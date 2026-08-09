"""
API para renderizar slideshow de álbum em MP4 via FFmpeg.
Job assíncrono — retorna slug para polling de status e link de compartilhamento.
"""
import os
import re
import json
import secrets
import subprocess
import threading
import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user
from app.models import SlideshowRenderJob, Media
from app.api.media import _auth_stream

router = APIRouter(prefix="/slideshow-render", tags=["slideshow-render"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class RenderItem(BaseModel):
    media_id: int
    media_type: str          # "image" | "video"
    display_rotation: int = 0
    duration: float = 5.0   # segundos (só para imagens)


class RenderRequest(BaseModel):
    album_id: Optional[int] = None
    album_name: str = "Slideshow"
    items: list[RenderItem]
    music_filename: Optional[str] = None   # arquivo em MUSIC_DIR
    photo_duration: float = 5.0            # segundos por foto (fallback)
    resolution: str = "1920x1080"          # landscape padrão (TV/celular deitado)


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_slideshows_dir() -> Path:
    d = settings.slideshows_dir.strip()
    if not d:
        raise HTTPException(status_code=400, detail="SLIDESHOWS_DIR não configurado no .env")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_filename(name: str) -> str:
    safe = re.sub(r'[^\w\-. ]', '_', name)
    return safe[:60].strip()


# ── Worker FFmpeg ─────────────────────────────────────────────────────────────

def _run_ffmpeg_render(job_id: int):
    """Delega para slideshow_engine — módulo leve sem FastAPI/matplotlib."""
    from app.services.slideshow_engine import run_render
    from app.core.database import engine as db_engine
    run_render(
        job_id=job_id,
        db_url=str(db_engine.url),
        ffmpeg=settings.ffmpeg_path or "ffmpeg",
        ffprobe=(getattr(settings, "ffprobe_path", None) or
                 (settings.ffmpeg_path or "ffmpeg").replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")),
        slideshows_dir=settings.slideshows_dir,
        music_dir=getattr(settings, "music_dir", "") or "",
    )


def _run_ffmpeg_render_UNUSED(job_id: int):
    db = SessionLocal()
    try:
        job = db.query(SlideshowRenderJob).get(job_id)
        if not job:
            return
        job.status = "running"
        job.updated_at = datetime.datetime.utcnow()
        db.commit()

        params = job.params or {}
        items = params.get("items", [])
        music_filename = params.get("music_filename")
        resolution = params.get("resolution", "1080x1920")
        album_name = params.get("album_name", "Slideshow")

        try:
            w, h = map(int, resolution.split("x"))
        except Exception:
            w, h = 1080, 1920

        ffmpeg = settings.ffmpeg_path or "ffmpeg"
        ffprobe = getattr(settings, "ffprobe_path", None) or ffmpeg.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
        out_dir = Path(settings.slideshows_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = job.slug
        out_path = out_dir / f"{slug}.mp4"
        tmp_dir = out_dir / f"tmp_{slug}"
        tmp_dir.mkdir(exist_ok=True)

        def _run(cmd_list, timeout=600, label="FFmpeg"):
            try:
                r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"{label} timeout após {timeout}s")
            if r.returncode != 0:
                raise RuntimeError(f"{label} falhou:\n{r.stderr[-1500:]}")
            return r

        def probe_duration(path: str) -> float:
            try:
                r = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", path],
                    capture_output=True, text=True, timeout=15)
                return max(0.1, float(r.stdout.strip()))
            except Exception:
                return 10.0

        def probe_has_audio(path: str) -> bool:
            try:
                r = subprocess.run(
                    [ffprobe, "-v", "error", "-select_streams", "a",
                     "-show_entries", "stream=codec_type",
                     "-of", "default=noprint_wrappers=1", path],
                    capture_output=True, text=True, timeout=10)
                return "audio" in r.stdout
            except Exception:
                return False

        # ── Helpers de filtro ──────────────────────────────────────────────────

        def _vf_with_blur_bg(rot: int) -> str:
            """filter_complex que compõe: fundo blur (cover) + imagem principal (contain) por cima."""
            if rot == 90:
                rotate_filter = "transpose=1,"
            elif rot == 270:
                rotate_filter = "transpose=2,"
            elif rot == 180:
                rotate_filter = "hflip,vflip,"
            else:
                rotate_filter = ""
            # Pre-scale para 1080p antes do split: blur opera em 1080p, nao em 8K
            pre = f"{rotate_filter}scale={w}:{h}:force_original_aspect_ratio=increase"
            fg = f"scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1"
            bg = f"crop={w}:{h},boxblur=20:20,eq=brightness=-0.2"
            return (f"[0:v]{pre}[prescaled];"
                    f"[prescaled]split=2[src1][src2];"
                    f"[src1]{bg}[bg];"
                    f"[src2]{fg}[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=24[out]")

        # ── Converte cada item para clipe uniforme H.264/AAC ──────────────────
        MAX_CLIPS = 50  # limite para evitar OOM com albums muito grandes
        if len(items) > MAX_CLIPS:
            items = items[:MAX_CLIPS]
        clip_paths = []
        total = len(items)

        # Fonte de imagem para o intro/outro (primeira foto disponível)
        intro_src = None
        outro_src = None

        for i, it in enumerate(items):
            mid = it.get("media_id")
            mtype = it.get("media_type", "image")
            rot = it.get("display_rotation", 0)
            dur = float(it.get("duration", 5.0))

            media = db.query(Media).get(mid)
            if not media:
                continue

            # Usa transcoded quando disponível (fotos 1920px, vídeos 960p — muito menor)
            if media.transcoded_path and Path(media.transcoded_path).exists():
                src = media.transcoded_path
            else:
                src = media.organized_path or media.original_path
            if not src or not Path(src).exists():
                continue

            # Guarda primeira e última foto para intro/outro
            if intro_src is None and mtype == "image":
                intro_src = src
            if mtype == "image":
                outro_src = src

            clip = str(tmp_dir / f"clip_{i:04d}.mp4")
            vf_complex = _vf_with_blur_bg(rot)

            if mtype == "image":
                _run([
                    ffmpeg, "-y",
                    "-loop", "1", "-t", str(dur), "-noautorotate", "-i", src,
                    "-f", "lavfi", "-t", str(dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                    "-filter_complex", vf_complex,
                    "-map", "[out]", "-map", "1:a",
                    "-c:v", "h264_qsv", "-global_quality", "26",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2",
                    "-shortest", clip,
                ], timeout=300, label=f"Clip imagem {i}")
            else:
                has_a = probe_has_audio(src)
                vid_dur = probe_duration(src)
                # Limita vídeos longos a 60s no slideshow
                max_vid = min(vid_dur, 60.0)
                if has_a:
                    vid_cmd = [ffmpeg, "-y", "-noautorotate", "-i", src,
                               "-t", str(max_vid),
                               "-filter_complex", vf_complex,
                               "-map", "[out]", "-map", "0:a",
                               "-c:v", "h264_qsv", "-global_quality", "26",
                               "-c:a", "aac", "-ar", "44100", "-ac", "2", clip]
                else:
                    vid_cmd = [ffmpeg, "-y", "-noautorotate", "-i", src,
                               "-f", "lavfi", "-t", str(max_vid), "-i", "aevalsrc=0:c=stereo:s=44100",
                               "-filter_complex", vf_complex,
                               "-map", "[out]", "-map", "1:a",
                               "-c:v", "h264_qsv", "-global_quality", "26",
                               "-c:a", "aac", "-ar", "44100", "-ac", "2",
                               "-shortest", clip]
                _run(vid_cmd, timeout=600, label=f"Clip vídeo {i}")

            clip_paths.append(clip)
            # Atualiza progresso
            job.progress = int((i + 1) / total * 80)
            job.updated_at = datetime.datetime.utcnow()
            db.commit()

        if not clip_paths:
            raise RuntimeError("Nenhum arquivo de mídia válido encontrado")

        # ── Gera clipe de INTRO (6s: nome do álbum + fundo blur da 1ª foto) ──
        intro_clip = str(tmp_dir / "clip_intro.mp4")
        intro_dur = 6.0
        safe_album = album_name.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        fontfile = "'C\\:/Windows/Fonts/arial.ttf'"
        fontfile_b = "'C\\:/Windows/Fonts/arialbd.ttf'"

        # Métricas do slideshow para exibir no intro
        n_photos = sum(1 for it in items if it.get("media_type") == "image")
        n_videos = sum(1 for it in items if it.get("media_type") == "video")
        total_dur_s = sum(float(it.get("duration", 5.0)) for it in items if it.get("media_type") == "image")
        total_dur_s += sum(min(probe_duration(
            (lambda m: (m.transcoded_path if m and m.transcoded_path and Path(m.transcoded_path).exists() else (m.organized_path or m.original_path)) if m else "")(db.query(Media).get(it.get("media_id")))), 60.0)
            for it in items if it.get("media_type") == "video")
        total_min = int(total_dur_s // 60)
        total_sec = int(total_dur_s % 60)
        dur_str = f"{total_min}min {total_sec:02d}s" if total_min else f"{total_sec}s"
        now_str = datetime.datetime.now().strftime("%d/%m/%Y")
        def _e(s): return s.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")
        line2 = _e(f"{now_str}  |  {dur_str}")
        line3 = _e(f"{n_photos} foto{'s' if n_photos != 1 else ''}  •  {n_videos} video{'s' if n_videos != 1 else ''}")

        if intro_src and Path(intro_src).exists():
            fade_expr = f"if(lt(t\\,0.8)\\,t/0.8\\,if(gt(t\\,{intro_dur-0.8:.1f})\\,({intro_dur:.1f}-t)/0.8\\,1))"
            cx = "(w-text_w)/2"
            cy_title = "(h-text_h)/2-60"
            cy_line2 = "(h-text_h)/2+20"
            cy_line3 = "(h-text_h)/2+70"
            intro_bg = (
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},boxblur=25:25,eq=brightness=-0.5[bg];"
                # título (bold, grande)
                f"[bg]drawtext=fontfile={fontfile_b}:text='{safe_album}':fontcolor=white:fontsize=68:"
                f"x={cx}:y={cy_title}:shadowcolor=black:shadowx=2:shadowy=2:alpha='{fade_expr}'[t1];"
                # data | duração
                f"[t1]drawtext=fontfile={fontfile}:text='{line2}':fontcolor=0xDDDDDD:fontsize=36:"
                f"x={cx}:y={cy_line2}:shadowcolor=black:shadowx=1:shadowy=1:alpha='{fade_expr}'[t2];"
                # nº fotos e vídeos
                f"[t2]drawtext=fontfile={fontfile}:text='{line3}':fontcolor=0xAAAAAA:fontsize=30:"
                f"x={cx}:y={cy_line3}:shadowcolor=black:shadowx=1:shadowy=1:alpha='{fade_expr}'[out]"
            )
            _run([
                ffmpeg, "-y",
                "-loop", "1", "-t", str(intro_dur), "-noautorotate", "-i", intro_src,
                "-f", "lavfi", "-t", str(intro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-filter_complex", intro_bg,
                "-map", "[out]", "-map", "1:a",
                "-c:v", "h264_qsv", "-global_quality", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest", intro_clip,
            ], timeout=60, label="Intro")
        else:
            # Intro sem foto: fundo preto com texto
            _run([
                ffmpeg, "-y",
                "-f", "lavfi", "-t", str(intro_dur), "-i", f"color=black:s={w}x{h}:r=24",
                "-f", "lavfi", "-t", str(intro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-vf", f"drawtext=text='{safe_album}':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=2:shadowy=2",
                "-c:v", "h264_qsv", "-global_quality", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-map", "0:v", "-map", "1:a",
                "-shortest", intro_clip,
            ], timeout=60, label="Intro (sem foto)")

        # ── Gera clipe de OUTRO (4s: "The End" + fundo blur da última foto) ──
        outro_clip = str(tmp_dir / "clip_outro.mp4")
        outro_dur = 4.0
        outro_bg_src = outro_src or intro_src
        if outro_bg_src and Path(outro_bg_src).exists():
            outro_fg = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                        f"crop={w}:{h},boxblur=25:25,eq=brightness=-0.5[bg];"
                        f"[bg]drawtext=fontfile={fontfile}:text='The End':fontcolor=white:fontsize=96:"
                        f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=3:shadowy=3[out]")
            _run([
                ffmpeg, "-y",
                "-loop", "1", "-t", str(outro_dur), "-noautorotate", "-i", outro_bg_src,
                "-f", "lavfi", "-t", str(outro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-filter_complex", outro_fg,
                "-map", "[out]", "-map", "1:a",
                "-c:v", "h264_qsv", "-global_quality", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest", outro_clip,
            ], timeout=60, label="Outro")
        else:
            _run([
                ffmpeg, "-y",
                "-f", "lavfi", "-t", str(outro_dur), "-i", f"color=black:s={w}x{h}:r=24",
                "-f", "lavfi", "-t", str(outro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-vf", "drawtext=text='The End':fontcolor=white:fontsize=80:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=3:shadowy=3",
                "-c:v", "h264_qsv", "-global_quality", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest", outro_clip,
            ], timeout=60, label="Outro (sem foto)")

        job.progress = 82
        db.commit()

        # ── Crossfade entre todos os clipes via xfade ─────────────────────────
        all_clips = [intro_clip] + clip_paths + [outro_clip]
        xf_target = 1.0  # segundos desejados de crossfade

        # Duração real de cada clip
        clip_durs = [probe_duration(c) for c in all_clips]

        silent_mp4 = str(tmp_dir / "concat_silent.mp4")

        if len(all_clips) == 1:
            import shutil as _sh
            _sh.copy2(all_clips[0], silent_mp4)
        else:
            # Usa -f concat com arquivo de lista: sem limite de inputs,
            # muito mais estável que filter_complex com 80+ inputs.
            # Todos os clips já estão normalizados (1920x1080, h264, aac 44100).
            concat_list = tmp_dir / "concat.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for c in all_clips:
                    f.write(f"file '{c.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
            _run(
                [ffmpeg, "-y",
                 "-f", "concat", "-safe", "0",
                 "-i", str(concat_list),
                 "-c", "copy",
                 "-movflags", "+faststart",
                 silent_mp4],
                timeout=600, label="Concat clips"
            )

        job.progress = 90
        db.commit()

        # ── Mixa música de fundo (opcional) ──────────────────────────────────
        if music_filename:
            music_path = Path(settings.music_dir) / music_filename
            if music_path.exists():
                _run([
                    ffmpeg, "-y",
                    "-i", silent_mp4,
                    "-stream_loop", "-1", "-i", str(music_path),
                    "-filter_complex",
                    "[0:a]volume=0.3[va];[1:a]volume=0.7[ma];[va][ma]amix=inputs=2:duration=first:dropout_transition=2[outa]",
                    "-map", "0:v", "-map", "[outa]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(out_path),
                ], timeout=600, label="Mix música")
            else:
                import shutil as _sh
                _sh.copy2(silent_mp4, str(out_path))
        else:
            _run([
                ffmpeg, "-y", "-i", silent_mp4,
                "-c", "copy", "-movflags", "+faststart",
                str(out_path),
            ], timeout=300, label="Faststart")

        job.status = "done"
        job.output_path = str(out_path)
        job.output_filename = out_path.name
        job.progress = 100

    except Exception as e:
        import traceback, logging
        logging.getLogger(__name__).error(
            f"[Slideshow job_id={job_id}] Erro inesperado: {e}\n{traceback.format_exc()}"
        )
        try:
            job = db.query(SlideshowRenderJob).get(job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)[:2000]
                job.updated_at = datetime.datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        try:
            import shutil as _sh
            if 'tmp_dir' in locals():
                _sh.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/start")
def start_render(req: RenderRequest, request: Request, token: Optional[str] = None, db: Session = Depends(get_db)):
    """Inicia renderização assíncrona. Retorna slug para polling."""
    _auth_stream(request, token)
    get_slideshows_dir()  # valida config

    slug = secrets.token_urlsafe(12)
    params = {
        "album_name": req.album_name,
        "items": [it.model_dump() for it in req.items],
        "music_filename": req.music_filename,
        "resolution": req.resolution,
        "photo_duration": req.photo_duration,
    }
    job = SlideshowRenderJob(
        album_id=req.album_id,
        slug=slug,
        status="pending",
        params=params,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Lança worker leve em processo separado — não carrega FastAPI/matplotlib/face_recognition
    import sys
    from app.core.database import engine as db_engine
    backend_dir = Path(__file__).parent.parent.parent
    worker = backend_dir / "slideshow_worker.py"
    ffmpeg = settings.ffmpeg_path or "ffmpeg"
    ffprobe = (getattr(settings, "ffprobe_path", None) or
               ffmpeg.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe"))
    music_dir = getattr(settings, "music_dir", "") or ""
    subprocess.Popen(
        [sys.executable, str(worker),
         str(job.id),
         str(db_engine.url),
         ffmpeg, ffprobe,
         settings.slideshows_dir,
         music_dir],
        cwd=str(backend_dir),
    )

    return {"slug": slug, "job_id": job.id, "status": "pending"}


@router.get("/status/{slug}")
def get_status(slug: str, db: Session = Depends(get_db)):
    """Polling do status do job. Público — o slug já é o segredo."""
    job = db.query(SlideshowRenderJob).filter(SlideshowRenderJob.slug == slug).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return {
        "slug": job.slug,
        "status": job.status,
        "progress": job.progress,
        "error_message": job.error_message,
        "output_filename": job.output_filename,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get("/list")
def list_renders(request: Request, token: Optional[str] = None, db: Session = Depends(get_db)):
    _auth_stream(request, token)
    """Lista todos os slideshows renderizados."""
    jobs = db.query(SlideshowRenderJob).order_by(SlideshowRenderJob.created_at.desc()).limit(100).all()
    return [
        {
            "slug": j.slug,
            "album_id": j.album_id,
            "album_name": (j.params or {}).get("album_name", ""),
            "status": j.status,
            "progress": j.progress,
            "output_filename": j.output_filename,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.delete("/{slug}")
def delete_render(slug: str, request: Request, token: Optional[str] = None, db: Session = Depends(get_db)):
    """Apaga o job e o arquivo MP4 do disco."""
    _auth_stream(request, token)
    job = db.query(SlideshowRenderJob).filter(SlideshowRenderJob.slug == slug).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    # Apaga arquivo físico se existir
    if job.output_path:
        try:
            Path(job.output_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(job)
    db.commit()
    return {"ok": True}


@router.get("/stream/{slug}")
def stream_render(slug: str, db: Session = Depends(get_db)):
    """Stream do MP4 renderizado. Público — o slug já é o segredo."""
    job = db.query(SlideshowRenderJob).filter(SlideshowRenderJob.slug == slug).first()
    if not job or job.status != "done":
        raise HTTPException(status_code=404, detail="Slideshow não disponível")
    p = Path(job.output_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no disco")
    return FileResponse(str(p), media_type="video/mp4", filename=job.output_filename)


@router.delete("/{slug}")
def delete_render(slug: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Remove job e arquivo MP4."""
    job = db.query(SlideshowRenderJob).filter(SlideshowRenderJob.slug == slug).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job.output_path:
        try:
            Path(job.output_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(job)
    db.commit()
    return {"ok": True}

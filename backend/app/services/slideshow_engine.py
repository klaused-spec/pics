"""
Motor de renderização de slideshow — sem FastAPI, sem face_recognition, sem matplotlib.
Pode ser importado pelo worker subprocess sem carregar a app inteira.
"""
import datetime
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def run_render(job_id: int, db_url: str, ffmpeg: str, ffprobe: str,
               slideshows_dir: str, music_dir: str = ""):
    """
    Renderiza o slideshow para o job_id dado.
    db_url: SQLAlchemy URL (ex: 'sqlite:///C:/src/pics/backend/pics.db')
    """
    from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime
    from sqlalchemy.orm import sessionmaker, declarative_base

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    db = Session()

    # Carrega modelos mínimos via SQL direto para não depender da app
    from sqlalchemy import text

    def get_job(jid):
        row = db.execute(text(
            "SELECT id, slug, album_id, status, progress, params FROM slideshow_render_jobs WHERE id=:id"
        ), {"id": jid}).fetchone()
        return row

    def update_job(jid, **kwargs):
        sets = ", ".join(f"{k}=:{k}" for k in kwargs)
        kwargs["id"] = jid
        kwargs["updated_at"] = datetime.datetime.utcnow().isoformat()
        db.execute(text(f"UPDATE slideshow_render_jobs SET {sets}, updated_at=:updated_at WHERE id=:id"), kwargs)
        db.commit()

    def get_media(mid):
        row = db.execute(text(
            "SELECT id, transcoded_path, organized_path, original_path FROM media WHERE id=:id"
        ), {"id": mid}).fetchone()
        return row

    job = get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} não encontrado no banco")
        return

    import json as _json
    params = _json.loads(job.params) if isinstance(job.params, str) else (job.params or {})
    items = params.get("items", [])
    music_filename = params.get("music_filename")
    resolution = params.get("resolution", "1920x1080")
    album_name = params.get("album_name", "Slideshow")
    slug = job.slug

    try:
        w, h = map(int, resolution.split("x"))
    except Exception:
        w, h = 1920, 1080

    out_dir = Path(slideshows_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug}.mp4"
    tmp_dir = out_dir / f"tmp_{slug}"
    tmp_dir.mkdir(exist_ok=True)

    update_job(job_id, status="running", progress=0)

    def _run(cmd_list, timeout=600, label="FFmpeg"):
        logger.info(f"[{label}] iniciando...")
        try:
            r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"{label} timeout após {timeout}s")
        if r.returncode != 0:
            raise RuntimeError(f"{label} falhou (rc={r.returncode}):\n{r.stderr[-2000:]}")
        logger.info(f"[{label}] OK")
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

    def _vf_with_blur_bg(rot: int) -> str:
        if rot == 90:
            rotate_filter = "transpose=1,"
        elif rot == 270:
            rotate_filter = "transpose=2,"
        elif rot == 180:
            rotate_filter = "hflip,vflip,"
        else:
            rotate_filter = ""
        # Scale down to 480p before blur (much faster), then upscale back
        bw = min(w, 480)
        bh = min(h, 270)
        pre = f"{rotate_filter}scale={w}:{h}:force_original_aspect_ratio=increase"
        fg = f"scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1"
        bg = f"crop={w}:{h},scale={bw}:{bh},boxblur=8:8,eq=brightness=-0.2,scale={w}:{h}"
        return (f"[0:v]{pre}[prescaled];"
                f"[prescaled]split=2[src1][src2];"
                f"[src1]{bg}[bg];"
                f"[src2]{fg}[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=24[out]")

    try:
        MAX_CLIPS = 50
        if len(items) > MAX_CLIPS:
            items = items[:MAX_CLIPS]

        clip_paths = []
        total = len(items)
        intro_src = None
        outro_src = None

        for i, it in enumerate(items):
            mid = it.get("media_id")
            mtype = it.get("media_type", "image")
            rot = it.get("display_rotation", 0)
            dur = float(it.get("duration", 5.0))

            media = get_media(mid)
            if not media:
                logger.warning(f"Media {mid} não encontrada, pulando")
                continue

            transcoded = media.transcoded_path
            organized = media.organized_path
            original = media.original_path

            if transcoded and Path(transcoded).exists():
                src = transcoded
            elif organized and Path(organized).exists():
                src = organized
            elif original and Path(original).exists():
                src = original
            else:
                logger.warning(f"Media {mid} sem arquivo válido, pulando")
                continue

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
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                    "-c:a", "aac", "-ar", "44100", "-ac", "2",
                    "-shortest", clip,
                ], timeout=300, label=f"Clip imagem {i}")
            else:
                has_a = probe_has_audio(src)
                vid_dur = probe_duration(src)
                max_vid = min(vid_dur, 60.0)
                if has_a:
                    vid_cmd = [
                        ffmpeg, "-y", "-noautorotate", "-i", src,
                        "-t", str(max_vid),
                        "-filter_complex", vf_complex,
                        "-map", "[out]", "-map", "0:a",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        "-c:a", "aac", "-ar", "44100", "-ac", "2", clip,
                    ]
                else:
                    vid_cmd = [
                        ffmpeg, "-y", "-noautorotate", "-i", src,
                        "-f", "lavfi", "-t", str(max_vid), "-i", "aevalsrc=0:c=stereo:s=44100",
                        "-filter_complex", vf_complex,
                        "-map", "[out]", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        "-c:a", "aac", "-ar", "44100", "-ac", "2",
                        "-shortest", clip,
                    ]
                _run(vid_cmd, timeout=600, label=f"Clip vídeo {i}")

            clip_paths.append(clip)
            update_job(job_id, progress=int((i + 1) / total * 80))

        if not clip_paths:
            raise RuntimeError("Nenhum arquivo de mídia válido encontrado")

        # ── Intro ─────────────────────────────────────────────────────────────
        intro_clip = str(tmp_dir / "clip_intro.mp4")
        intro_dur = 6.0
        fontfile = "'C\\:/Windows/Fonts/arial.ttf'"
        fontfile_b = "'C\\:/Windows/Fonts/arialbd.ttf'"

        def _e(s):
            return s.replace("'", "\\'").replace(":", "\\:").replace(",", "\\,")

        safe_album = _e(album_name)
        n_photos = sum(1 for it in items if it.get("media_type") == "image")
        n_videos = sum(1 for it in items if it.get("media_type") == "video")
        total_dur_s = sum(float(it.get("duration", 5.0)) for it in items if it.get("media_type") == "image")
        for it in items:
            if it.get("media_type") == "video":
                m = get_media(it.get("media_id"))
                if m:
                    src_v = (m.transcoded_path if m.transcoded_path and Path(m.transcoded_path).exists()
                             else (m.organized_path or m.original_path or ""))
                    total_dur_s += min(probe_duration(src_v), 60.0) if src_v else 0
        total_min = int(total_dur_s // 60)
        total_sec = int(total_dur_s % 60)
        dur_str = f"{total_min}min {total_sec:02d}s" if total_min else f"{total_sec}s"
        now_str = datetime.datetime.now().strftime("%d/%m/%Y")
        line2 = _e(f"{now_str}  |  {dur_str}")
        line3 = _e(f"{n_photos} foto{'s' if n_photos != 1 else ''}  •  {n_videos} video{'s' if n_videos != 1 else ''}")

        fade_expr = f"if(lt(t\\,0.8)\\,t/0.8\\,if(gt(t\\,{intro_dur-0.8:.1f})\\,({intro_dur:.1f}-t)/0.8\\,1))"
        cx = "(w-text_w)/2"

        if intro_src and Path(intro_src).exists():
            intro_bg = (
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},scale=480:270,boxblur=8:8,eq=brightness=-0.5,scale={w}:{h}[bg];"
                f"[bg]drawtext=fontfile={fontfile_b}:text='{safe_album}':fontcolor=white:fontsize=68:"
                f"x={cx}:y=(h-text_h)/2-60:shadowcolor=black:shadowx=2:shadowy=2:alpha='{fade_expr}'[t1];"
                f"[t1]drawtext=fontfile={fontfile}:text='{line2}':fontcolor=0xDDDDDD:fontsize=36:"
                f"x={cx}:y=(h-text_h)/2+20:shadowcolor=black:shadowx=1:shadowy=1:alpha='{fade_expr}'[t2];"
                f"[t2]drawtext=fontfile={fontfile}:text='{line3}':fontcolor=0xAAAAAA:fontsize=30:"
                f"x={cx}:y=(h-text_h)/2+70:shadowcolor=black:shadowx=1:shadowy=1:alpha='{fade_expr}'[out]"
            )
            _run([
                ffmpeg, "-y",
                "-loop", "1", "-t", str(intro_dur), "-noautorotate", "-i", intro_src,
                "-f", "lavfi", "-t", str(intro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-filter_complex", intro_bg,
                "-map", "[out]", "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest", intro_clip,
            ], timeout=60, label="Intro")
        else:
            _run([
                ffmpeg, "-y",
                "-f", "lavfi", "-t", str(intro_dur), "-i", f"color=black:s={w}x{h}:r=24",
                "-f", "lavfi", "-t", str(intro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-vf", f"drawtext=text='{safe_album}':fontcolor=white:fontsize=64:"
                       f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=2:shadowy=2",
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest", intro_clip,
            ], timeout=60, label="Intro (sem foto)")

        # ── Outro ─────────────────────────────────────────────────────────────
        outro_clip = str(tmp_dir / "clip_outro.mp4")
        outro_dur = 4.0
        outro_bg_src = outro_src or intro_src
        if outro_bg_src and Path(outro_bg_src).exists():
            outro_fg = (
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},scale=480:270,boxblur=8:8,eq=brightness=-0.5,scale={w}:{h}[bg];"
                f"[bg]drawtext=fontfile={fontfile}:text='The End':fontcolor=white:fontsize=96:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=3:shadowy=3[out]"
            )
            _run([
                ffmpeg, "-y",
                "-loop", "1", "-t", str(outro_dur), "-noautorotate", "-i", outro_bg_src,
                "-f", "lavfi", "-t", str(outro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-filter_complex", outro_fg,
                "-map", "[out]", "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest", outro_clip,
            ], timeout=60, label="Outro")
        else:
            _run([
                ffmpeg, "-y",
                "-f", "lavfi", "-t", str(outro_dur), "-i", f"color=black:s={w}x{h}:r=24",
                "-f", "lavfi", "-t", str(outro_dur), "-i", "aevalsrc=0:c=stereo:s=44100",
                "-vf", "drawtext=text='The End':fontcolor=white:fontsize=80:"
                       "x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=3:shadowy=3",
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-shortest", outro_clip,
            ], timeout=60, label="Outro (sem foto)")

        update_job(job_id, progress=82)

        # ── Concat ────────────────────────────────────────────────────────────
        all_clips = [intro_clip] + clip_paths + [outro_clip]
        silent_mp4 = str(tmp_dir / "concat_silent.mp4")

        if len(all_clips) == 1:
            shutil.copy2(all_clips[0], silent_mp4)
        else:
            concat_list = tmp_dir / "concat.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for c in all_clips:
                    safe_c = c.replace("\\", "/")
                    f.write(f"file '{safe_c}'\n")
            _run([
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                "-movflags", "+faststart",
                silent_mp4,
            ], timeout=600, label="Concat clips")

        update_job(job_id, progress=90)

        # ── Música (opcional) ─────────────────────────────────────────────────
        if music_filename and music_dir:
            music_path = Path(music_dir) / music_filename
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
                shutil.copy2(silent_mp4, str(out_path))
        else:
            _run([
                ffmpeg, "-y", "-i", silent_mp4,
                "-c", "copy", "-movflags", "+faststart",
                str(out_path),
            ], timeout=300, label="Faststart")

        update_job(job_id, status="done", progress=100,
                   output_path=str(out_path),
                   output_filename=out_path.name)
        logger.info(f"Slideshow job {job_id} concluído: {out_path}")

    except Exception as exc:
        logger.exception(f"Slideshow job {job_id} falhou: {exc}")
        update_job(job_id, status="failed", error_message=str(exc)[:2000])
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass

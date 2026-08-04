# Desabilitar Boot de Disco USB GPT (sem mexer na BIOS)

## O que foi tentado e por quê não funcionou

| Método | Resultado |
|--------|-----------|
| Mudar GUID da partição ESP para Basic Data | UEFI ignorou — bootou mesmo assim via fallback |
| Renomear `BOOTX64.EFI` | UEFI travou no boot em vez de tentar o próximo dispositivo |

---

## Método que funciona — Mover o bootloader para subpasta

O UEFI procura especificamente por `\EFI\BOOT\BOOTX64.EFI`. Mover o arquivo para uma subpasta faz o disco ser ignorado **sem travar** o processo de boot — o UEFI simplesmente não encontra o arquivo e passa para o próximo dispositivo.

### Passo 1 — Montar a partição ESP

```
diskpart
select disk 2
select partition 1
assign letter=Z
exit
```

### Passo 2 — Obter acesso à partição (como Administrador)

```powershell
takeown /f Z:\EFI\BOOT /r /d s
icacls Z:\EFI\BOOT /grant Administrators:F /t
```

### Passo 3 — Mover o bootloader para subpasta

```powershell
New-Item -ItemType Directory -Path Z:\EFI\BOOT\disabled -Force
Move-Item Z:\EFI\BOOT\BOOTX64.EFI Z:\EFI\BOOT\disabled\BOOTX64.EFI
```

### Restaurar quando quiser

```powershell
Move-Item Z:\EFI\BOOT\disabled\BOOTX64.EFI Z:\EFI\BOOT\BOOTX64.EFI
```

### Passo 4 — Desmontar a partição

```
diskpart
select disk 2
select partition 1
remove letter=Z
exit
```

---

## Notas

- **Renomear** o arquivo trava o boot em vez de pular para o próximo dispositivo — por isso mover é preferível.
- Mudar o GUID da partição não é suficiente; muitos UEFIs fazem fallback e ignoram o tipo da partição.
- Nenhum dado é perdido; o bootloader continua no disco, apenas fora do caminho esperado pelo UEFI.
- Este método **não funciona em discos MBR** (use `inactive`/`active` nesses casos).

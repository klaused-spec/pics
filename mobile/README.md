# PICS Mobile

App Android em Expo para navegar a biblioteca PICS com thumbnails locais.

## Fluxo

- Login no backend FastAPI usando o mesmo usuário da interface web.
- Sync baixa `/api/media/sync/manifest` em páginas.
- Cada thumbnail é salvo em `FileSystem.documentDirectory/thumbs` para navegar offline.
- Ao tocar em uma mídia, o app baixa o arquivo full para `FileSystem.documentDirectory/full` e abre a cópia local.
- Em próximos acessos, o arquivo full já cacheado abre imediatamente.

## Rodar

```powershell
cd mobile
npm install
npm run android
```

No Android físico, o app vem apontando para `https://pics.meulavoro.com.br:8443`. Se estiver usando apenas rede local, troque para a URL LAN do backend, por exemplo `http://192.168.0.10:8000`.

## Gerar APK (teste/sideload)

O build acontece no GitHub Actions (workflow `Android APK`), sem precisar de Android SDK local.
Dispare manualmente em **Actions > Android APK > Run workflow** ou faça push em `mobile/**`.
Se os secrets de assinatura estiverem configurados (ver abaixo), o APK sai assinado
com a keystore de upload e permite atualizar por cima sem desinstalar.

> Sideload (instalar o `.apk` fora da Play Store) sempre mostra avisos de "fonte
> desconhecida"/Play Protect. Isso é comportamento do Android e **não** some por
> assinar o APK — só some publicando na Play Store.

## Publicar na Google Play Store (elimina os avisos)

Este é o único caminho que remove o aviso de "app não verificado / desenvolvedor
desconhecido" para o usuário final.

### 1. Gerar a keystore de upload (uma vez, local, guarde em cofre)

```powershell
$ksPath = "$env:USERPROFILE\pics-upload-key.jks"
keytool -genkeypair -v `
  -keystore $ksPath `
  -alias pics-upload `
  -keyalg RSA -keysize 2048 -validity 10000 `
  -storetype JKS
```

Anote: senha da keystore, senha da key e o alias (`pics-upload`).

### 2. Cadastrar os GitHub Secrets

Converta a keystore em base64 e copie para a área de transferência:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\pics-upload-key.jks")) | Set-Clipboard
```

Em **GitHub > Settings > Secrets and variables > Actions**, crie:

| Secret | Valor |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | (o base64 copiado acima) |
| `ANDROID_KEYSTORE_PASSWORD` | senha da keystore |
| `ANDROID_KEY_ALIAS` | `pics-upload` |
| `ANDROID_KEY_PASSWORD` | senha da key |

### 3. Gerar o AAB assinado

Em **Actions > Android AAB (Play Store) > Run workflow**. O artefato
`pics-mobile-release-aab` contém o `.aab` para enviar à Play.

### 4. Enviar ao Play Console

1. Crie o app em <https://play.google.com/console> (conta de desenvolvedor: taxa única de US$ 25).
2. Ative **Play App Signing** (padrão) — o Google guarda a chave final; você só
   envia AAB assinado com a chave de upload. Se perder a chave de upload, o
   suporte do Google reseta para você.
3. Faça upload do `.aab` em **Testes internos** (mais rápido) ou **Produção**.
4. Preencha ficha da loja (ícone 512×512, screenshots, política de privacidade),
   classificação de conteúdo e questionário de segurança de dados.
5. Publique. Depois de aprovado, quem instalar pela Play **não vê** avisos de fonte
   desconhecida.

### Atualizações futuras

Suba `android.versionCode` em `app.json` (ex.: 1 → 2) e o `version`, dispare o
workflow do AAB e envie a nova versão ao Play Console.

> A keystore (`.jks`), `keystore.properties` e a pasta `mobile/android/` estão no
> `.gitignore` e **nunca** devem ser commitados.
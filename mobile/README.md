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

No Android físico, use a URL LAN do backend, por exemplo `http://192.168.0.10:8000`.

## Gerar APK

Esta máquina precisa de Android SDK + JDK moderno para build local. Sem isso, use EAS Build:

```powershell
cd mobile
npx eas-cli build -p android --profile preview
```

O perfil `preview` em `eas.json` gera APK instalável. Ao final, o EAS mostra o link para baixar o `.apk`.
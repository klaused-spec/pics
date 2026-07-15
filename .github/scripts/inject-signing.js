#!/usr/bin/env node
/*
 * Injeta uma release signingConfig no app/build.gradle gerado pelo
 * `expo prebuild`. As credenciais sao lidas de android/keystore.properties
 * (que e criado no workflow a partir de GitHub Secrets e apagado depois).
 *
 * Idempotente: se ja houver a marca PICS_SIGNING, nao faz nada.
 */
const fs = require('fs');
const path = require('path');

const gradlePath = path.resolve(__dirname, '..', '..', 'mobile', 'android', 'app', 'build.gradle');

if (!fs.existsSync(gradlePath)) {
  console.error(`build.gradle nao encontrado em ${gradlePath}. Rode o prebuild antes.`);
  process.exit(1);
}

let gradle = fs.readFileSync(gradlePath, 'utf8');

if (gradle.includes('PICS_SIGNING')) {
  console.log('signingConfig ja injetada. Nada a fazer.');
  process.exit(0);
}

// 1) Loader das propriedades no topo do arquivo (apos a linha `apply plugin` inicial nao e obrigatorio,
//    mas colocamos antes do bloco android { ... } para garantir disponibilidade).
const propsLoader = `
// PICS_SIGNING: carrega credenciais de assinatura de keystore.properties
def picsKeystorePropsFile = rootProject.file("keystore.properties")
def picsKeystoreProps = new Properties()
if (picsKeystorePropsFile.exists()) {
    picsKeystoreProps.load(new FileInputStream(picsKeystorePropsFile))
}
`;

// Insere o loader imediatamente antes do bloco `android {`.
const androidBlockIndex = gradle.search(/\nandroid\s*\{/);
if (androidBlockIndex === -1) {
  console.error('Bloco `android {` nao encontrado no build.gradle.');
  process.exit(1);
}
gradle = gradle.slice(0, androidBlockIndex) + '\n' + propsLoader + gradle.slice(androidBlockIndex);

// 2) Adiciona signingConfigs.release dentro do bloco android { ... }.
//    Inserimos logo apos a abertura do bloco android {.
const signingConfigBlock = `
    signingConfigs {
        release {
            if (picsKeystoreProps.getProperty("storeFile") != null) {
                storeFile file(picsKeystoreProps.getProperty("storeFile"))
                storePassword picsKeystoreProps.getProperty("storePassword")
                keyAlias picsKeystoreProps.getProperty("keyAlias")
                keyPassword picsKeystoreProps.getProperty("keyPassword")
            }
        }
    }
`;

gradle = gradle.replace(/\nandroid\s*\{/, `\nandroid {\n${signingConfigBlock}`);

// 3) Faz o buildType release usar a signingConfig.release.
//    Procura o bloco `release {` dentro de buildTypes e troca a signingConfig debug por release.
if (/buildTypes\s*\{[\s\S]*?release\s*\{/.test(gradle)) {
  gradle = gradle.replace(
    /(release\s*\{[\s\S]*?)signingConfig\s+signingConfigs\.debug/,
    '$1signingConfig signingConfigs.release'
  );
  // Caso o release nao tenha nenhuma signingConfig declarada, adiciona uma.
  if (!/release\s*\{[\s\S]*?signingConfig\s+signingConfigs\.release/.test(gradle)) {
    gradle = gradle.replace(
      /(buildTypes\s*\{[\s\S]*?release\s*\{)/,
      '$1\n            signingConfig signingConfigs.release'
    );
  }
} else {
  console.error('Bloco buildTypes.release nao encontrado. Verifique o build.gradle gerado.');
  process.exit(1);
}

fs.writeFileSync(gradlePath, gradle, 'utf8');
console.log('signingConfig de release injetada com sucesso em app/build.gradle');

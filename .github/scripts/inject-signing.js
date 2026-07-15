#!/usr/bin/env node
/*
 * Injeta uma release signingConfig no app/build.gradle gerado pelo
 * `expo prebuild`. As credenciais sao lidas de android/keystore.properties
 * (criado no workflow a partir de GitHub Secrets e apagado depois).
 *
 * Estrategia (robusta, com casamento de chaves balanceadas em vez de regex fragil):
 *   1. Insere um loader de keystore.properties antes do bloco `android {`.
 *   2. Adiciona um signingConfigs.release DENTRO do bloco signingConfigs { }
 *      ja existente (o Expo gera um com `debug`).
 *   3. No sub-bloco buildTypes { release { ... } }, troca a linha
 *      `signingConfig signingConfigs.debug` por `signingConfig signingConfigs.release`
 *      (ou adiciona a linha caso nao exista) -- SEM afetar o bloco debug.
 *
 * Idempotente: se ja houver a marca PICS_SIGNING, nao faz nada.
 */
const fs = require('fs');
const path = require('path');

const gradlePath = path.resolve(__dirname, '..', '..', 'mobile', 'android', 'app', 'build.gradle');

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

if (!fs.existsSync(gradlePath)) {
  fail(`build.gradle nao encontrado em ${gradlePath}. Rode o prebuild antes.`);
}

let gradle = fs.readFileSync(gradlePath, 'utf8');

if (gradle.includes('PICS_SIGNING')) {
  console.log('signingConfig ja injetada. Nada a fazer.');
  process.exit(0);
}

/** Retorna o indice do `}` que fecha o bloco cujo `{` esta em openBraceIndex. */
function matchBrace(text, openBraceIndex) {
  let depth = 0;
  for (let i = openBraceIndex; i < text.length; i++) {
    const ch = text[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/** Encontra o indice da `{` de um bloco nomeado (ex.: "android", "signingConfigs"). */
function findBlockOpenBrace(text, blockName, fromIndex = 0) {
  const re = new RegExp(`(^|\\n)[ \\t]*${blockName}[ \\t]*\\{`, 'g');
  re.lastIndex = fromIndex;
  const m = re.exec(text);
  if (!m) return -1;
  return m.index + m[0].lastIndexOf('{');
}

// ---- 1) Loader das propriedades, antes do bloco `android {` ----
const propsLoader = `// PICS_SIGNING: carrega credenciais de assinatura de keystore.properties
def picsKeystorePropsFile = rootProject.file("keystore.properties")
def picsKeystoreProps = new Properties()
if (picsKeystorePropsFile.exists()) {
    picsKeystoreProps.load(new FileInputStream(picsKeystorePropsFile))
}

`;

const androidBraceIdx = findBlockOpenBrace(gradle, 'android');
if (androidBraceIdx === -1) fail('Bloco `android {` nao encontrado no build.gradle.');

const androidLineStart = gradle.lastIndexOf('\n', androidBraceIdx) + 1;
gradle = gradle.slice(0, androidLineStart) + propsLoader + gradle.slice(androidLineStart);

// ---- 2) Adiciona release dentro do signingConfigs { } existente ----
const releaseSigning = `
        release {
            if (picsKeystoreProps.getProperty("storeFile") != null) {
                storeFile file(picsKeystoreProps.getProperty("storeFile"))
                storePassword picsKeystoreProps.getProperty("storePassword")
                keyAlias picsKeystoreProps.getProperty("keyAlias")
                keyPassword picsKeystoreProps.getProperty("keyPassword")
            }
        }`;

const signingConfigsBrace = findBlockOpenBrace(gradle, 'signingConfigs');
if (signingConfigsBrace !== -1) {
  gradle =
    gradle.slice(0, signingConfigsBrace + 1) +
    releaseSigning +
    gradle.slice(signingConfigsBrace + 1);
} else {
  const aBrace = findBlockOpenBrace(gradle, 'android');
  const block = `\n    signingConfigs {${releaseSigning}\n    }\n`;
  gradle = gradle.slice(0, aBrace + 1) + block + gradle.slice(aBrace + 1);
}

// ---- 3) buildTypes.release deve usar signingConfigs.release ----
const buildTypesBrace = findBlockOpenBrace(gradle, 'buildTypes');
if (buildTypesBrace === -1) fail('Bloco `buildTypes {` nao encontrado.');
const buildTypesEnd = matchBrace(gradle, buildTypesBrace);
if (buildTypesEnd === -1) fail('Nao foi possivel casar chaves de buildTypes.');

let buildTypes = gradle.slice(buildTypesBrace, buildTypesEnd + 1);

const releaseBraceRel = findBlockOpenBrace(buildTypes, 'release');
if (releaseBraceRel === -1) fail('Bloco `release {` dentro de buildTypes nao encontrado.');
const releaseEndRel = matchBrace(buildTypes, releaseBraceRel);
if (releaseEndRel === -1) fail('Nao foi possivel casar chaves de buildTypes.release.');

let releaseBlock = buildTypes.slice(releaseBraceRel, releaseEndRel + 1);

if (/signingConfig\s+signingConfigs\.\w+/.test(releaseBlock)) {
  releaseBlock = releaseBlock.replace(
    /signingConfig\s+signingConfigs\.\w+/,
    'signingConfig signingConfigs.release'
  );
} else {
  releaseBlock =
    releaseBlock.slice(0, 1) +
    '\n            signingConfig signingConfigs.release' +
    releaseBlock.slice(1);
}

buildTypes =
  buildTypes.slice(0, releaseBraceRel) + releaseBlock + buildTypes.slice(releaseEndRel + 1);
gradle = gradle.slice(0, buildTypesBrace) + buildTypes + gradle.slice(buildTypesEnd + 1);

fs.writeFileSync(gradlePath, gradle, 'utf8');
console.log('signingConfig de release injetada com sucesso em app/build.gradle');

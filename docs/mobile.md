# Mobile projects — toolchain0.243.0

The current receipts for 0.243.0 cover both mobile hosts. iOS:
[mobile iOS](evidence/mobile-ios-0.243.0-2026-11-13.json) generated a Capacitor
project, built it with Xcode for the iOS 27.1 simulator, installed/launched
`dev.nex.mobile243` and captured the actual NEX Tasks UI. Android:
[mobile Android](evidence/mobile-android-0.243.0-2026-11-13.json) generated the
Android project, built `app-debug.apk` with JDK21/API36 and launched
`dev.nex.mobile243/.MainActivity` on an arm64 Android 16 emulator with the actual
NEX Tasks UI. An additional
[Android interaction receipt](evidence/mobile-android-interaction-0.243.0-2026-11-13.json)
uses adb input to add `ShipNEX` (2 active) and mark it complete (1 active, struck
through with Mark active), proving the typed update path in the living app.
Device signing and store delivery remain separate pending steps.

## Historical toolchain0.63 receipt

`tools/mobile_project.py` generates iOS and Android projects from the existing
checked NEX web application contract. Business state, transitions and views stay
in NEX; TypeScript/React output runs in the native host's WebView. Capacitor8.5.3
provides the native platform host. The separate native iOS archive target uses
MLIR/LLVM and is not automatically linked into this UI path.

Generation, native compilation, signing, installation and actual UI execution
are separate steps. The0.63 simulator/emulator application checks are recorded
in [development evidence](evidence/toolchain-0.63.0.json). The earlier local-origin
rejection and failed input automation attempts are retained with the corrected
UI checks. A generated project alone does not establish a running application.

## Generate

Use Node22.18+, npm and a built/installed matching NEX compiler. Declare the same
pure initial/update/view/title contract described in `docs/web.md`.

```sh
python3 /actual/sdk/share/nex/tools/mobile_project.py /actual/project/main.nex \
  --nex /actual/sdk/bin/nex --directory /new/mobile-project \
  --platform both --app-id dev.example.app --name 'My NEX App' \
  --artifact-cache /actual/dependency-cache
```

The output parent must exist, while the output itself must be new. An existing
directory or symlink is refused. The app ID uses2..8 lowercase ASCII dot-separated
identifiers without Java keywords; the label allows1..80 Unicode scalars and at
most256 UTF-8 bytes without controls. `--platform ios` or `android` generates
one native project. `--profile debug|release` selects the browser build profile.
It does not select the native platform's build configuration.

The generator builds only reachable client/shared code through the checked web
backend, copies its assets and notices, installs exact locked Capacitor packages
with lifecycle scripts disabled, and writes native project files. iOS framework
archives are SHA-256 pinned to the matching upstream Swift package and unpacked
under bounded file/size/path rules. The generated Swift package references local
frameworks, so Xcode does not resolve a second remote binary dependency.

Add `--offline` when npm's cache and both checked native archives are already
available. `NEX_NPM_CACHE`, `NEX_NODE` and `NEX_NPM` select development tools/cache.
The artifact cache stores `<sha256>.zip`; absent or changed offline content is
rejected. Downloads never install a simulator or platform SDK and do not accept
new platform license agreements. The generator's output includes
`nex-mobile-project.json`, exact web asset hashes, dependency pins, logs and
explicit `native_application_built:false` / `target_executed:false`. A failure
retains the new project and logs for inspection. It does not overwrite input code.

## Native build and run

For iOS, use macOS and a compatible Xcode. The generated project is
`ios/App/App.xcodeproj`, scheme `App`. A local simulator build can use:

```sh
xcodebuild -project ios/App/App.xcodeproj -scheme App -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' -configuration Debug \
  -derivedDataPath /new/derived-data -disableAutomaticPackageResolution \
  CODE_SIGNING_ALLOWED=NO build
```

Use an available matching Simulator runtime, create/select the intended test
device, install the reported `.app` with `simctl install`, then launch its actual
bundle ID. Check the living app and actual UI, including input, navigation and
narrow/alternate displays. On a multi-display simulator explicitly select its
primary display; the default screenshot can capture an inactive secondary panel.
Device deployment, provisioning/signing and App Store delivery need their own
platform workflow and account. They are not performed by this generator.

For Android, install a compatible ARM64/x86-64 JDK21, Android API36 and build-tools
through the platform's own tooling. Set `JAVA_HOME` and `ANDROID_HOME` to their
actual paths, then run `android/gradlew :app:assembleDebug` from `android/`.
The generator removes an inferred `local.properties` so it cannot silently pin
an unrelated build-machine SDK. Select the SDK explicitly at build time.
A debug APK must be installed/launched on an explicit owned emulator/device and
its UI checked. Release signing and store delivery remain separate.

## Boundaries

Mobile host dependencies are pinned in `mobile/package-lock.json` and
`mobile/ios-artifacts.json`; browser dependencies and their notices retain their
existing separate lock. The generated assets include mobile runtime/source MIT
licenses and Apache/Cordova notices. Platform build dependencies and application
plugins require their own matching inventories/notices. No native plugins or
new privileged device capabilities are granted by NEX source in this adapter.

Relative routes/assets are allowed only on the exact local iOS
`capacitor://localhost` origin with no credentials/port. Explicit custom-scheme
URLs, authority-relative paths and unrelated opaque origins are rejected.
Ordinary HTTP(S)/mail/tel link rules remain. Without an explicit API override,
network commands require an HTTP(S) application origin. The operator can select
one HTTPS API origin as described below. Background services, native plugin
bindings, store deployment and a stable native Swift/JNI ABI remain pending. An embedded WebView does not establish native UI rendering or a general
performance advantage. General source async/GPU support is unchanged.

## Remote API

Pass `--api-origin https://api.example.test` to configure one HTTPS API origin.
The generated app remains bundled locally; the host only changes the request
destination. Runtime credentials, exact server CORS origins, TLS trust,
asset provenance and current validation scope are described in
[mobile API configuration](mobile-api.md). Offline state-only apps omit this
option. Actual HTTPS API operation is verified on an ARM64 iOS27.1 Simulator and an
ARM64 Android16/API36 emulator, with runtime credentials and an owned test CA.
The iOS XCTest uses native keyboard paste for long credentials; earlier bulk
`typeText` and menu attempts are retained. Physical devices, production PKI and
release signing require separate validation.

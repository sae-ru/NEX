param(
  [string]$BuildDirectory,
  [string]$HostPrefix,
  [string]$TargetPrefix,
  [string]$SQLiteRoot,
  [string]$CMake='C:\Program Files\CMake\bin\cmake.exe'
)
$ErrorActionPreference='Stop'
$nexRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if(!$BuildDirectory){$BuildDirectory=Join-Path $nexRoot 'build/windows-host'}
if(!$HostPrefix){$HostPrefix=Join-Path $nexRoot 'build/deps/windows-host/clang64'}
if(!$TargetPrefix){$TargetPrefix=Join-Path $nexRoot 'build/deps/llvm-mingw-20260616-ucrt-x86_64'}
if(!$SQLiteRoot){$SQLiteRoot=Join-Path $nexRoot 'build/deps/sqlite-windows'}
$BuildDirectory=[IO.Path]::GetFullPath($BuildDirectory)
$HostPrefix=[IO.Path]::GetFullPath($HostPrefix)
$TargetPrefix=[IO.Path]::GetFullPath($TargetPrefix)
$SQLiteRoot=[IO.Path]::GetFullPath($SQLiteRoot)
New-Item -ItemType Directory -Path $BuildDirectory -Force > $null
# The Windows LLVM-MinGW ZIP shares headers at prefix/include. Keep the
# architecture sysroot shape used by the exact header/library fingerprint.
foreach($nexArchitecture in @('x86_64','aarch64')){
  $nexSysroot=Join-Path $TargetPrefix ($nexArchitecture+'-w64-mingw32')
  $nexHeaders=Join-Path $nexSysroot 'include'
  if((Test-Path -LiteralPath $nexSysroot) -and !(Test-Path -LiteralPath $nexHeaders)){
    $nexCommonHeaders=Join-Path $TargetPrefix 'include'
    if(!(Test-Path -LiteralPath (Join-Path $nexCommonHeaders '_mingw.h'))){throw 'LLVM-MinGW common headers are missing'}
    New-Item -ItemType Junction -Path $nexHeaders -Target $nexCommonHeaders > $null
  }
}
$nexNoticeFiles=@((Join-Path $TargetPrefix 'LICENSE.TXT'))+@(Get-ChildItem -LiteralPath (Join-Path $TargetPrefix 'x86_64-w64-mingw32/share/mingw32') -Filter 'COPYING*' -File | Sort-Object Name | ForEach-Object FullName)
$nexCryptoPrefix=Join-Path $nexRoot 'build/deps/openssl-windows'
New-Item -ItemType Directory -Path (Join-Path $nexCryptoPrefix 'include'),(Join-Path $nexCryptoPrefix 'x86_64') -Force > $null
if(!(Test-Path -LiteralPath (Join-Path $nexCryptoPrefix 'include/openssl'))){
  New-Item -ItemType Junction -Path (Join-Path $nexCryptoPrefix 'include/openssl') -Target (Join-Path $HostPrefix 'include/openssl') > $null
}
foreach($nexCryptoLibrary in @('libcrypto.a','libssl.a')){
  Copy-Item -LiteralPath (Join-Path $HostPrefix ('lib/'+$nexCryptoLibrary)) -Destination (Join-Path $nexCryptoPrefix ('x86_64/'+$nexCryptoLibrary))
}
Copy-Item -LiteralPath (Join-Path $HostPrefix 'share/licenses/openssl/LICENSE') -Destination (Join-Path $nexCryptoPrefix 'LICENSE')
$nexNoticeFiles+=Join-Path $nexCryptoPrefix 'LICENSE'
$nexNotices=[IO.MemoryStream]::new()
foreach($nexNoticeFile in $nexNoticeFiles){
  $nexBytes=[IO.File]::ReadAllBytes($nexNoticeFile);$nexNotices.Write($nexBytes,0,$nexBytes.Length)
  $nexNotices.WriteByte(10);$nexNotices.WriteByte(10)
}
$nexNoticePath=Join-Path $BuildDirectory 'windows-runtime-notices.txt'
[IO.File]::WriteAllBytes($nexNoticePath,$nexNotices.ToArray());$nexNotices.Dispose()
$nexConfiguration=[ordered]@{
  schema='nex.toolchain/1';target='x86_64-w64-windows-gnu'
  compiler=(Join-Path $TargetPrefix 'bin/clang++.exe').Replace('\','/')
  linker=(Join-Path $TargetPrefix 'bin/ld.lld.exe').Replace('\','/')
  archiver=(Join-Path $TargetPrefix 'bin/llvm-ar.exe').Replace('\','/')
  sysroot=(Join-Path $TargetPrefix 'x86_64-w64-mingw32').Replace('\','/')
  windows=@{runtime='ucrt-static';notices=$nexNoticePath.Replace('\','/')}
  sqlite=@{include=(Join-Path $SQLiteRoot 'sqlite-amalgamation-3540100').Replace('\','/');library=(Join-Path $SQLiteRoot 'x86_64/libsqlite3.a').Replace('\','/')}
  openssl=@{include=(Join-Path $nexCryptoPrefix 'include').Replace('\','/');ssl=(Join-Path $nexCryptoPrefix 'x86_64/libssl.a').Replace('\','/');crypto=(Join-Path $nexCryptoPrefix 'x86_64/libcrypto.a').Replace('\','/')}
}
$nexConfigurationPath=Join-Path $BuildDirectory 'toolchain.json'
[IO.File]::WriteAllText($nexConfigurationPath,($nexConfiguration | ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
$env:PATH=(Join-Path $HostPrefix 'bin')+';'+$env:PATH
& $CMake -S $nexRoot -B $BuildDirectory -G Ninja -DCMAKE_BUILD_TYPE=Release `
  "-DCMAKE_C_COMPILER=$HostPrefix/bin/clang.exe" "-DCMAKE_CXX_COMPILER=$HostPrefix/bin/clang++.exe" `
  "-DCMAKE_MAKE_PROGRAM=$HostPrefix/bin/ninja.exe" "-DCMAKE_PREFIX_PATH=$HostPrefix" `
  "-DOPENSSL_ROOT_DIR=$HostPrefix" "-DNEX_Z3_ROOT=$HostPrefix" "-DNEX_DEFAULT_TOOLCHAIN=$($nexConfigurationPath.Replace('\','/'))"
exit $LASTEXITCODE

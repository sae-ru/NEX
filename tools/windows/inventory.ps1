param([string]$Output, [string]$LLVMMinGWRoot)
$ErrorActionPreference='Stop'
$os=Get-CimInstance Win32_OperatingSystem
$cpu=Get-CimInstance Win32_Processor
$gpu=Get-CimInstance Win32_VideoController
$version=Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$report=[ordered]@{
  schema='nex.windows-inventory/1'; environment='native Windows'
  os=$os.Caption; version=$os.Version; build=$os.BuildNumber; update_revision=$version.UBR
  architecture=$os.OSArchitecture; RAM_bytes=($os.TotalVisibleMemorySize*1024)
  cpu=@($cpu | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
  gpu=@($gpu | Select-Object Name,DriverVersion,DriverDate)
  tools=[ordered]@{}
}
$commands=@{git=@('--version');python=@('--version');node=@('--version');'nvidia-smi'=@('--query-gpu=name,driver_version,pci.bus_id,memory.total','--format=csv,noheader');nvcc=@('--version')}
foreach($name in $commands.Keys){
  $command=Get-Command $name -ErrorAction SilentlyContinue
  if($command){$report.tools[$name]=@{path=$command.Source;version=((& $command.Source @($commands[$name]) 2>&1 | Out-String).Trim())}}
}
$cmake='C:\Program Files\CMake\bin\cmake.exe'
if(Test-Path -LiteralPath $cmake){$report.tools.cmake=@{path=$cmake;version=((& $cmake --version | Out-String).Trim())}}
$vswhere='C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
if(Test-Path -LiteralPath $vswhere){$report.visual_studio=@(& $vswhere -all -format json | ConvertFrom-Json | Select-Object installationPath,installationVersion)}
if($LLVMMinGWRoot){
  $report.tools.llvm_mingw=@{path=$LLVMMinGWRoot;version=((& (Join-Path $LLVMMinGWRoot 'bin/clang++.exe') --version | Out-String).Trim())}
}
$json=$report | ConvertTo-Json -Depth 8
if($Output){[IO.File]::WriteAllText($Output,$json,[Text.UTF8Encoding]::new($false))}else{$json}

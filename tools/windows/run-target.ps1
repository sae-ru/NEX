param(
  [string]$Source='main.nex',
  [Parameter(Mandatory=$true)][string]$Toolchain,
  [ValidateSet('debug','release')][string]$Profile='release',
  [string]$Entry='main',
  [string]$Distro='Ubuntu-22.04',
  [string]$Producer='/home/sae/nex-build/nex',
  [string[]]$ProgramArguments=@()
)
# An explicit WSL producer followed by a native Windows process, not a
# Windows-hosted NEX SDK. No environment/file/foreign grants are added here.
$ErrorActionPreference='Stop'
function LinuxPath([string]$Path){
  $resolved=[IO.Path]::GetFullPath($Path).Replace('\','/')
  if($resolved -notmatch '^([A-Za-z]):/(.*)$'){throw 'Use a local Windows drive path'}
  return '/mnt/'+$Matches[1].ToLowerInvariant()+'/'+$Matches[2]
}
$working=LinuxPath (Get-Location).Path
$configuration=LinuxPath (Resolve-Path -LiteralPath $Toolchain).Path
$inputSource=if([IO.Path]::IsPathRooted($Source)){LinuxPath $Source}else{$Source.Replace('\','/')}
$output=& wsl.exe -d $Distro --cd $working -- $Producer build $inputSource --entry $Entry --toolchain $configuration --profile $Profile --json
$buildExit=$LASTEXITCODE
if($buildExit){$output | Write-Output;exit $buildExit}
$built=$output | ConvertFrom-Json
if($built.compiler_target -ne 'x86_64-w64-windows-gnu'){throw 'This runner requires an x86_64 Windows GNU PE'}
if($built.executable -notmatch '^/mnt/([a-z])/(.+)$'){throw 'Build the artifact on a mounted Windows drive'}
$executable=$Matches[1].ToUpperInvariant()+':/'+$Matches[2]
& $executable @ProgramArguments
exit $LASTEXITCODE

[CmdletBinding()]
param(
    [ValidateSet('setup', 'serve', 'test', 'release', 'cloudflare-login', 'pages', 'deploy')]
    [string]$Action = 'test',
    [string]$ProjectName = 'power-accessible-mail'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$toolDirectory = Join-Path $root '.tools\node-v24.18.0-win-x64'
$node = Join-Path $toolDirectory 'node.exe'
$npm = Join-Path $toolDirectory 'npm.cmd'
$wrangler = Join-Path $root 'node_modules\wrangler\bin\wrangler.js'

if (-not (Test-Path -LiteralPath $node)) {
    throw "Local Node.js is missing. Expected: $node"
}

$env:Path = "$toolDirectory;$env:Path"
Set-Location -LiteralPath $root

switch ($Action) {
    'setup' { & $npm install }
    'serve' { & $npm run serve }
    'test' { & $npm run check }
    'release' { & $npm run check:release }
    'cloudflare-login' { & $node $wrangler login }
    'pages' { & $node $wrangler pages project list }
    'deploy' {
        & $npm run check
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $node $wrangler pages deploy dist --project-name $ProjectName
    }
}

exit $LASTEXITCODE

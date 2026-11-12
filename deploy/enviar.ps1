# Envia o Agendu do seu Windows para o servidor e coloca no ar.
#
# Primeira vez (instala tudo no servidor, ao lado do Ativix):
#   .\deploy\enviar.ps1 -Servidor root@187.41.119.140 -Instalar -Dominio agendu.ativix.co -Email voce@email.com
#
# Atualizações:
#   .\deploy\enviar.ps1 -Servidor root@187.41.119.140
param(
    [Parameter(Mandatory = $true)][string]$Servidor,
    [switch]$Instalar,
    [string]$Dominio,
    [string]$Email
)

$raiz = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pacote = Join-Path $env:TEMP "agendu.tar.gz"

if ($Instalar -and (-not $Dominio -or -not $Email)) {
    Write-Host "Na primeira instalação informe -Dominio e -Email (o e-mail é para o certificado HTTPS)." -ForegroundColor Red
    exit 1
}

Write-Host "==> Rodando os testes antes de enviar..."
Push-Location $raiz
cmd /c ".venv\Scripts\python.exe manage.py test 2>&1" | Select-Object -Last 3
$ok = $LASTEXITCODE
Pop-Location
if ($ok -ne 0) { Write-Host "Os testes falharam; nada foi enviado." -ForegroundColor Red; exit 1 }

Write-Host "==> Empacotando o código..."
$excluir = @(".venv", "db.sqlite3", "privado", "staticfiles", ".cache", "__pycache__", ".git")
$argumentos = @("-czf", $pacote, "-C", $raiz)
foreach ($e in $excluir) { $argumentos += "--exclude=./$e" }
$argumentos += "--exclude=__pycache__"
$argumentos += "."
& "$env:SystemRoot\System32\tar.exe" @argumentos
if ($LASTEXITCODE -ne 0) { Write-Host "Falha ao empacotar." -ForegroundColor Red; exit 1 }
Write-Host ("    {0:N1} MB" -f ((Get-Item $pacote).Length / 1MB))

Write-Host "==> Enviando para $Servidor..."
scp $pacote "${Servidor}:/tmp/agendu.tar.gz"
if ($LASTEXITCODE -ne 0) { Write-Host "Falha no envio (confira o IP e a chave SSH)." -ForegroundColor Red; exit 1 }

# Extrai os scripts do pacote numa pasta temporária e roda o certo (aspas simples: o PowerShell não mexe no $ do sed).
$preparar = 'rm -rf /tmp/agendu-pacote && mkdir -p /tmp/agendu-pacote && tar -xzf /tmp/agendu.tar.gz -C /tmp/agendu-pacote ./deploy && sed -i "s/\r$//" /tmp/agendu-pacote/deploy/*.sh'
if ($Instalar) {
    $comando = "$preparar && sudo bash /tmp/agendu-pacote/deploy/instalar_servidor.sh '$Dominio' '$Email' /tmp/agendu.tar.gz"
} else {
    $comando = "$preparar && sudo bash /tmp/agendu-pacote/deploy/atualizar.sh /tmp/agendu.tar.gz"
}
Write-Host "==> Instalando no servidor..."
ssh -t $Servidor $comando
if ($LASTEXITCODE -ne 0) { Write-Host "Algo falhou no servidor; veja as mensagens acima." -ForegroundColor Red; exit 1 }
Write-Host "Concluído." -ForegroundColor Green

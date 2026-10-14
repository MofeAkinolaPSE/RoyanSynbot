<#
  issue-cert-dns.ps1 - get the real (browser-trusted) HTTPS certificate for RoyanHealth from Let's Encrypt.

  RoyanHealth is reached on https://<DOMAIN>:9443 because ports 80/443 of the hospital's public IP belong to
  Placeware. Let's Encrypt cannot check the domain on port 80, so the domain is proven through its DNS: certbot
  puts a temporary TXT record in the domain's Cloudflare DNS (with the API token in certbot-secrets\cloudflare.ini),
  Let's Encrypt reads it, and the certificate is issued. Renewal afterwards is automatic (the certbot container).

  Run ONCE on the server, in Windows PowerShell, from <APP_FOLDER>\deploy:

      powershell -ExecutionPolicy Bypass -File .\issue-cert-dns.ps1 -Email <EMAIL> -Domain <DOMAIN>

  Safe to run again: a valid certificate is kept, not re-issued.
#>
param(
    [Parameter(Mandatory = $true)][string]$Email,
    [Parameter(Mandatory = $true)][string]$Domain,
    [switch]$SkipPractice
)
$ErrorActionPreference = "Continue"
function Step($n, $text) { Write-Host ""; Write-Host "[$n] $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    OK  $text" -ForegroundColor Green }
function Fail($text, $help) {
    Write-Host "    FAILED  $text" -ForegroundColor Red
    if ($help) { Write-Host "    $help" -ForegroundColor Yellow }
    exit 1
}
$dns = @("--dns-cloudflare", "--dns-cloudflare-credentials", "/secrets/cloudflare.ini", "--dns-cloudflare-propagation-seconds", "30")

# 1 ------------------------------------------------------------------------------------------
Step 1 "Checking Docker and the Cloudflare token"
if (-not (Test-Path ".\docker-compose.yml")) { Fail "Run this from <APP_FOLDER>\deploy." }
docker version --format "{{.Server.Version}}" *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker is not running." "Open Docker Desktop, wait for 'Engine running', run again." }
$ini = ".\certbot-secrets\cloudflare.ini"
if (-not (Test-Path $ini)) { Fail "No $ini." "Copy certbot-secrets\cloudflare.ini.example to cloudflare.ini and paste the Cloudflare API token into it." }
if ((Get-Content $ini -Raw) -match "PASTE-THE-TOKEN-HERE") { Fail "The token in $ini is still the placeholder." "Paste the Cloudflare API token (walkthrough Step 6)." }
docker compose up -d nginx certbot | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "Could not start nginx and certbot." "Run: docker compose ps   and   docker compose logs nginx" }
Ok "Docker up, token present, nginx and certbot running"

# 2 ------------------------------------------------------------------------------------------
if (-not $SkipPractice) {
    Step 2 "Practice run with Let's Encrypt's TEST servers (nothing is changed)"
    docker compose run --rm --entrypoint certbot certbot certonly @dns -d $Domain `
        --email $Email --agree-tos --no-eff-email --non-interactive --dry-run
    if ($LASTEXITCODE -ne 0) {
        Fail "The DNS check failed for $Domain." "Check: (a) the domain's nameservers are Cloudflare's (Cloudflare shows the domain as Active), (b) the token uses the 'Edit zone DNS' template for this domain, (c) the token was pasted without spaces."
    }
    Ok "Let's Encrypt can verify $Domain through its DNS"
}

# 3 ------------------------------------------------------------------------------------------
Step 3 "Getting the real certificate"
docker compose run --rm --entrypoint certbot certbot certonly @dns -d $Domain `
    --email $Email --agree-tos --no-eff-email --non-interactive --keep-until-expiring
if ($LASTEXITCODE -ne 0) { Fail "Let's Encrypt did not issue the certificate." "Read the message above. If it mentions 'too many', wait an hour - Let's Encrypt limits repeated attempts." }
Ok "certificate issued"

# 4 ------------------------------------------------------------------------------------------
Step 4 "Installing it and reloading the web server"
docker compose run --rm --entrypoint sh certbot -c "cp -L /etc/letsencrypt/live/$Domain/fullchain.pem /etc/nginx/ssl/cert.pem && cp -L /etc/letsencrypt/live/$Domain/privkey.pem /etc/nginx/ssl/key.pem && chmod 644 /etc/nginx/ssl/cert.pem && chmod 640 /etc/nginx/ssl/key.pem"
if ($LASTEXITCODE -ne 0) { Fail "Could not copy the certificate into place." "Run: docker compose logs certbot" }
docker compose exec nginx nginx -s reload
if ($LASTEXITCODE -ne 0) { Fail "nginx did not reload." "Run: docker compose restart nginx" }
docker compose up -d certbot | Out-Null
Ok "certificate installed, nginx reloaded, automatic renewal running"

Write-Host ""
docker compose run --rm --entrypoint certbot certbot certificates
Write-Host ""
Write-Host "Done. Open https://${Domain}:9443 - the padlock should show with no warning." -ForegroundColor Green
Write-Host "(If a browser still warns, close ALL its windows and reopen - it can remember the old certificate.)"

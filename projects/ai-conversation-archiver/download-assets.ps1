param(
    [Parameter(Mandatory = $true)]
    [string]$RawDir,
    [Parameter(Mandatory = $true)]
    [string]$AttachmentDir
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$manifestPath = Join-Path $attachmentDir 'download-manifest.json'
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$client = [System.Net.Http.HttpClient]::new()
$results = [System.Collections.Generic.List[object]]::new()

try {
    $files = Get-ChildItem -LiteralPath $rawDir -File -Filter '*.json' |
        Where-Object { $_.Name -ne '_manifest.json' }

    foreach ($file in $files) {
        $conversation = Get-Content -Raw -Encoding UTF8 -LiteralPath $file.FullName |
            ConvertFrom-Json
        $conversationId = [string]$conversation.conversation_id
        $destinationDir = Join-Path $attachmentDir $conversationId

        foreach ($asset in @($conversation.assets)) {
            $url = [string]$asset.url
            if ([string]::IsNullOrWhiteSpace($url)) {
                continue
            }

            $hashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
            try {
                $hashBytes = $hashAlgorithm.ComputeHash(
                    [System.Text.Encoding]::UTF8.GetBytes($url)
                )
            }
            finally {
                $hashAlgorithm.Dispose()
            }
            $hash = ([System.BitConverter]::ToString($hashBytes) -replace '-', '').
                Substring(0, 16).ToLowerInvariant()

            try {
                $response = $client.GetAsync($url).GetAwaiter().GetResult()
                try {
                    $response.EnsureSuccessStatusCode()
                    $contentType = [string]$response.Content.Headers.ContentType.MediaType
                    $extension = switch -Regex ($contentType) {
                        '^image/png$' { '.png'; break }
                        '^image/jpeg$' { '.jpg'; break }
                        '^image/webp$' { '.webp'; break }
                        '^image/gif$' { '.gif'; break }
                        '^video/mp4$' { '.mp4'; break }
                        default {
                            if ([string]$asset.kind -eq 'image') { '.img' }
                            elseif ([string]$asset.kind -eq 'video') { '.video' }
                            else { '.bin' }
                        }
                    }

                    if (-not (Test-Path -LiteralPath $destinationDir)) {
                        New-Item -ItemType Directory -Path $destinationDir | Out-Null
                    }
                    $destination = Join-Path $destinationDir ($hash + $extension)
                    $bytes = $response.Content.ReadAsByteArrayAsync().
                        GetAwaiter().GetResult()
                    [System.IO.File]::WriteAllBytes($destination, $bytes)

                    $results.Add([pscustomobject]@{
                        conversation_id = $conversationId
                        title = [string]$conversation.title
                        source_url = $url
                        kind = [string]$asset.kind
                        content_type = $contentType
                        local_path = $destination
                        file_name = [System.IO.Path]::GetFileName($destination)
                        bytes = $bytes.Length
                        status = 'downloaded'
                        error = ''
                    })
                }
                finally {
                    $response.Dispose()
                }
            }
            catch {
                $results.Add([pscustomobject]@{
                    conversation_id = $conversationId
                    title = [string]$conversation.title
                    source_url = $url
                    kind = [string]$asset.kind
                    content_type = ''
                    local_path = ''
                    file_name = ''
                    bytes = 0
                    status = 'failed'
                    error = $_.Exception.Message
                })
            }
        }
    }
}
finally {
    $client.Dispose()
}

$manifest = [pscustomobject]@{
    generated_at = (Get-Date).ToString('o')
    total = $results.Count
    downloaded = @($results | Where-Object status -eq 'downloaded').Count
    failed = @($results | Where-Object status -eq 'failed').Count
    results = $results
}
[System.IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 8),
    $utf8NoBom
)

$manifest | Select-Object total, downloaded, failed

param(
    [string]$FramesDir,
    [string]$OutputFile
)

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]

function Await($WinRtTask, $ResultType) {
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | `
        Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("zh-CN"))
if ($null -eq $engine) {
    Write-Output "ENGINE_NULL"
    exit 2
}

$frames = Get-ChildItem -Path $FramesDir -Filter "f_*.jpg" | Sort-Object Name
$lines = New-Object System.Collections.Generic.List[string]

foreach ($frame in $frames) {
    $index = [int]($frame.BaseName -replace 'f_', '')
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($frame.FullName)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $text = ($result.Text -replace '\s', '')
        $lines.Add("$index|$text")
    } catch {
        $lines.Add("$index|OCR_ERROR")
    }
}

[System.IO.File]::WriteAllLines($OutputFile, $lines, [System.Text.Encoding]::UTF8)
Write-Output ("DONE " + $lines.Count)

' PDV Joao & Maria - abre o sistema em janela propria, sem navegador aparente.
' 1. Se o servidor nao estiver no ar, inicia escondido (sem janela preta).
' 2. Abre a janela do PDV em modo aplicativo (sem abas e sem endereco).
' Clicar de novo no icone so abre a janela; nao duplica o servidor.

Option Explicit

Const URL_HEALTH = "http://127.0.0.1:8000/health"
Const URL_APP = "http://127.0.0.1:8000/"

Dim sh, fso, pasta, navegador, perfil, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

pasta = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = pasta

Function ServidorNoAr()
    Dim http
    ServidorNoAr = False
    On Error Resume Next
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts 1000, 1000, 1000, 1000
    http.Open "GET", URL_HEALTH, False
    http.Send
    If Err.Number = 0 Then
        If http.Status = 200 Then ServidorNoAr = True
    End If
    On Error GoTo 0
End Function

Function AcharNavegador()
    Dim candidatos, c, caminho
    candidatos = Array( _
        "%ProgramFiles%\Google\Chrome\Application\chrome.exe", _
        "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe", _
        "%LocalAppData%\Google\Chrome\Application\chrome.exe", _
        "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe", _
        "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")
    AcharNavegador = ""
    For Each c In candidatos
        caminho = sh.ExpandEnvironmentStrings(c)
        If fso.FileExists(caminho) Then
            AcharNavegador = caminho
            Exit Function
        End If
    Next
End Function

If Not ServidorNoAr() Then
    sh.Run "cmd /c "".venv\Scripts\python.exe -m alembic upgrade head && " & _
           ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000""", 0, False
    For i = 1 To 60
        WScript.Sleep 500
        If ServidorNoAr() Then Exit For
    Next
    If Not ServidorNoAr() Then
        MsgBox "O PDV nao conseguiu iniciar." & vbCrLf & vbCrLf & _
               "Use o atalho DIAGNOSTICO e envie o resultado para o Gabriel.", _
               vbCritical, "PDV Joao & Maria"
        WScript.Quit 1
    End If
End If

navegador = AcharNavegador()
If navegador = "" Then
    MsgBox "Nao encontrei o Chrome nem o Edge neste computador.", vbCritical, "PDV Joao & Maria"
    WScript.Quit 2
End If

perfil = sh.ExpandEnvironmentStrings("%LocalAppData%\PDV-Padaria\janela")
sh.Run """" & navegador & """ --app=" & URL_APP & _
       " --user-data-dir=""" & perfil & """" & _
       " --start-maximized --no-first-run --no-default-browser-check" & _
       " --disable-features=Translate", 1, False

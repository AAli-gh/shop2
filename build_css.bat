@echo off
rem Build Tailwind CSS: build_css.bat [watch]
cd /d "%~dp0"
if "%1"=="watch" (
    tools\tailwindcss.exe -i static\css\input.css -o static\css\site.css --watch
) else (
    tools\tailwindcss.exe -i static\css\input.css -o static\css\site.css --minify
)

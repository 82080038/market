#!/bin/bash
# Restart Devin Desktop bersih — kill semua proses lama, lalu start ulang
# Gunakan saat Devin crash atau terasa berat
set -e

echo "==> Mematikan semua proses Devin Desktop..."
pkill -f 'devin-desktop' 2>/dev/null || true
pkill -f 'devin acp' 2>/dev/null || true
pkill -f 'language_server_linux' 2>/dev/null || true
pkill -f 'claude-agent-acp' 2>/dev/null || true
pkill -f 'copilot.*acp' 2>/dev/null || true
pkill -f 'qwen.*acp' 2>/dev/null || true

sleep 2

echo "==> Membersihkan cache Electron yang sudah tidak terpakai..."
rm -rf /home/petrick/.config/Devin/Cache/Cache_Data/* 2>/dev/null || true
rm -rf /home/petrick/.config/Devin/GPUCache/* 2>/dev/null || true
rm -rf /home/petrick/.config/Devin/Code Cache/* 2>/dev/null || true

echo "==> Memeriksa memori sebelum start ulang..."
free -h

echo "==> Menjalankan Devin Desktop..."
nohup /usr/share/devin-desktop/devin-desktop >/dev/null 2>&1 &

sleep 3
echo "==> Status proses Devin setelah restart:"
ps aux | grep -E 'devin-desktop|devin acp|language_server' | grep -v grep | awk '{printf "PID=%-8s RSS=%-8sKB  %s\n", $2, $6, $11}'

echo ""
echo "==> Selesai. Cek memori:"
free -h

#!/bin/bash

# Активируем виртуальное окружение
echo "Activating the virtual environment..."
source venv/bin/activate

# Запускаем основной скрипт
echo "Running modem detection..."
python start_modem.py
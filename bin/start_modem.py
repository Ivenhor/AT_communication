import subprocess
import os
import json
import time
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from modem import Modem  # Импортируем класс Modem

def run_modem_finder():
    """Запускает основной скрипт поиска модема и опроса после нахождения"""
    modem = Modem()

    # Находим порт модема
    modem_port = modem.find_modem_port()

    if modem_port:
        print(f"Modem found on port: {modem_port}")
        
        # Открываем соединение с модемом
        modem.open_modem_connection(modem_port)
        
        # После успешного подключения отправляем AT команды из JSON файла
        modem.send_at_commands_from_json('commands.json')  # Передаем путь к файлу JSON

        # Закрываем соединение с модемом после выполнения команд
        modem.close_modem_connection()

    else:
        print("Modem not found.")

if __name__ == "__main__":
    run_modem_finder()

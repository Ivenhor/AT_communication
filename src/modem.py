import logging
import serial
import serial.tools.list_ports
import json
import time
import platform
from colorama import Fore, Style
from tabulate import tabulate
import os

logging.basicConfig(
    level=logging.ERROR,  # Устанавливаем уровень логирования на DEBUG
    format='%(asctime)s - %(levelname)s - %(message)s'  # Формат вывода
)

class Modem:
    def __init__(self):
        self.modem_port = None
        self.ser = None
        self.log_dir = "logs"
        parent_dir = os.path.abspath(os.path.join(os.getcwd(), ".."))  # Получаем родительскую директорию
        self.log_path = os.path.join(parent_dir, self.log_dir)

        # Создаем папку 'logs', если она не существует
        if not os.path.exists(self.log_path):
            os.makedirs(self.log_path)

        # Указываем путь к лог-файлу внутри папки 'logs'
        self.log_file = os.path.join(self.log_path, "modem_log.txt")

    def find_modem_port(self):
        """Checks all available ports and searches for a modem that responds to AT commands."""
        # Add a short delay after connecting the device to allow initialization
        time.sleep(2)

        # Get a list of all available COM ports
        ports = serial.tools.list_ports.comports()

        if not ports:
            logging.error("No ports available. Ensure the modem is connected.")
            return None

        # Determine the OS
        current_os = platform.system()

        if current_os == "Windows":
            # Windows: filter ports by description and search for "Quectel USB Modem"
            logging.debug("Running on Windows. Filtering ports by description: 'Quectel USB Modem'")
            target_description = "Quectel USB Modem"
            return self._find_modem_on_ports(ports, target_description)

        else:  # Assume Linux or other
            logging.debug(f"Running on {current_os}. Filtering ports by 'ttyUSB' for Linux-based systems")
            port_filter = "ttyUSB"
            return self._find_modem_on_ports(ports, port_filter)

    def _find_modem_on_ports(self, ports, filter_criteria):
        """Helper function to find modem on ports based on filter criteria (Windows or Linux)."""
        for port in ports:
            if filter_criteria not in port.device and filter_criteria not in port.description:
                logging.debug(f"Skipping port: {port.device}")
                continue
            try:
                ser = serial.Serial(port.device, baudrate=115200, timeout=1)
                logging.debug(f"Trying port: {port.device}")

                # Send the AT command
                ser.write(b'AT\r')
                time.sleep(1)

                # Read the response
                response = ser.read_all().decode().strip()
                logging.debug(f"Response from {port.device}: {response}")

                # If the response contains "OK", this is our modem
                if "OK" in response:
                    self.print_table([["Modem found", f"on port: {port.device}"]], Fore.GREEN)
                    ser.close()  # Close the port
                    return port.device
                ser.close()

            except serial.SerialException as e:
                logging.error(f"Error on port {port.device}: {e}")
            except IOError as e:
                logging.debug(f"I/O Error on port {port.device}: {e}")

        # If the modem is not found after the retry
        logging.error("Modem not found on any available ports.")
        self.print_table([["Modem not found", "on any available ports."]], Fore.RED)
        return None
    

    def open_modem_connection(self, port):
        """Открывает соединение с модемом на указанном порту."""
        try:
            self.ser = serial.Serial(port, baudrate=115200, timeout=1)
            logging.info(f"Соединение с модемом на порту {port} установлено.")
        except serial.SerialException as e:
            logging.error(f"Ошибка соединения с портом {port}: {e}")
            self.ser = None

    def close_modem_connection(self):
        """Закрывает соединение с модемом."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            logging.info("Соединение с модемом закрыто.")

    def send_at_commands_from_json(self, json_file):
        """Парсит команды из JSON файла и отправляет их модему."""
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            commands = data.get("commands", [])
            if not commands:
                logging.error("Не найдены команды в JSON файле.")
                return

            # Отправляем команды с задержкой между ними
            for cmd in commands:
                command = cmd.get("command")
                expected_response = cmd.get("expected_response")

                if command:
                    # Если команда - QFUPL, добавить размер файла и таймаут
                    if command.startswith("AT+QFUPL"):
                        filename = command.split('"')[1]
                        file_path = os.path.join("..", "serts", filename)

                        # Проверяем наличие файла
                        if not os.path.exists(file_path):
                            logging.error(f"Файл {file_path} не найден.")
                            continue

                        # Определяем размер файла и рассчитываем таймаут
                        file_size = os.path.getsize(file_path)
                        timeout = max(20, file_size // 100)  # минимальный таймаут 20, или пропорционально размеру

                        # Формируем полную команду с размером и таймаутом
                        command = f'AT+QFUPL="{filename}",{file_size},{timeout}'

                    # Отправляем команду
                    self.ser.write(f"{command}\r".encode())
                    time.sleep(1)  # Задержка между командами
                    self.log_command_and_response(command, None)


                    # Если команда - QFUPL и ответ "CONNECT", отправить файл
                    if command.startswith("AT+QFUPL"):
                        self._upload_file(filename)
                        continue

                    # Если команда - QFDEL, просто передаем команду без загрузки
                    elif command.startswith("AT+QFDEL"):
                        self._delete_file(command)
                        continue

                                        # Чтение ответа
                    response = self.ser.read_all().decode().strip()

                    self.log_command_and_response(command, response)

                    # Вывод команды и ответа в таблицу
                    self.print_table([[command, response]], Fore.GREEN if expected_response in response else Fore.RED)


        except FileNotFoundError:
            logging.error(f"Файл {json_file} не найден.")
        except json.JSONDecodeError:
            logging.error("Ошибка декодирования JSON файла.")
        except Exception as e:
            logging.error(f"Ошибка при отправке команд: {e}")


    def _upload_file(self, filename):
        """Выполняет загрузку файла на модем, ожидая ответ CONNECT перед передачей файла."""
        try:
            # Путь к файлу
            file_path = os.path.join("..", "serts", filename)
            
            # Логируем путь к файлу
            logging.debug(f"Путь к файлу: {file_path}")
            
            # Проверка, существует ли файл
            if not os.path.exists(file_path):
                logging.error(f"Файл {file_path} не найден.")
                self.print_table([[filename, "File not found"]], Fore.RED)
                return

            # Отправляем команду AT+QFUPL для начала загрузки файла
            file_size = os.path.getsize(file_path)
            timeout = max(20, file_size // 100)  # Минимальный таймаут 20, или пропорционально размеру
            logging.debug(f"Размер файла: {file_size} байт, Таймаут: {timeout} секунд")

            # Логируем отправленную команду
            at_command = f"AT+QFUPL=\"{filename}\",{file_size},{timeout}\r"
            logging.debug(f"Отправленная команда: {at_command}")
            self.ser.write(at_command.encode())
            time.sleep(2)  # Даем модему время на обработку команды
            
            # Чтение ответа от модема
            response = self.ser.read_all().decode().strip()
            logging.debug(f"Ответ от модема: {response}")

            self.log_command_and_response(at_command, response)
            
            # Проверяем, готов ли модем к загрузке
            if "CONNECT" in response:
                logging.info("Modem ready for file upload. Sending file data...")

                # Чтение файла и отправка данных
                with open(file_path, "rb") as file:
                    file_data = file.read()
                    self.ser.write(file_data)  # Отправляем файл
                    logging.debug(f"Файл {filename} отправлен модему.")
                
                # Ожидаем финальный ответ от модема, который должен содержать размер загруженного файла
                time.sleep(2)
                final_response = self.ser.read_all().decode().strip()
                logging.debug(f"Финальный ответ от модема: {final_response}")
                self.log_command_and_response(f"Sending file: {filename}", final_response)
                
                # Проверяем, что в ответе от модема указан размер файла, и сравниваем с реальным размером
                if final_response.startswith("+QFUPL:"):
                    # Извлекаем размер из ответа модема
                    parts = final_response.split(":")[1].split(",")
                    modem_file_size = int(parts[0].strip())  # Размер из ответа модема
                    
                    if modem_file_size == file_size:
                        self.print_table([[filename, "File upload successful"]], Fore.GREEN)
                        logging.info(f"Загрузка файла {filename} завершена успешно.")
                    else:
                        self.print_table([[filename, f"File size mismatch: expected {file_size}, got {modem_file_size}"]], Fore.RED)
                        logging.error(f"Ошибка загрузки файла {filename}: размер не совпадает. Ожидался {file_size}, получен {modem_file_size}")
                else:
                    self.print_table([[filename, "Invalid modem response"]], Fore.RED)
                    logging.error(f"Неверный ответ от модема: {final_response}")
            else:
                logging.error("Modem not ready for file upload.")
                self.print_table([[filename, response]], Fore.RED)
                
        except Exception as e:
            logging.error(f"Ошибка при загрузке файла: {e}")
            self.print_table([[filename, f"Error: {e}"]], Fore.RED)


    def _delete_file(self, command):
        """Удаляет файл с помощью команды AT+QFDEL."""
        try:
            # Отправляем команду AT+QFDEL
            self.ser.write(f"{command}\r".encode())
            time.sleep(1)  # Задержка между командами

            # Чтение ответа
            response = self.ser.read_all().decode().strip()

            # Логируем фактический ответ от модема и команду для сравнения
            logging.debug(f"Получен ответ от модема: '{response}' для команды: '{command}'")
            self.log_command_and_response(command, response)
            # Обработка ответа:
            if "OK" in response:
                # Если ответ OK, то файл успешно удален
                self.print_table([[command, "File deleted successfully"]], Fore.GREEN)
            elif "+CME ERROR: 418" in response:
                # Если ошибка CME 418, файл не найден
                try:
                    # Извлекаем имя файла из команды
                    file_name = command.split('"')[1]
                    logging.info(f"Файл не найден для удаления: {file_name}. Пропускаем удаление.")
                    self.print_table([[command, "File not found"]], Fore.YELLOW)
                except IndexError:
                    logging.error("Ошибка при разборе команды для удаления файла.")
                    self.print_table([[command, "Error parsing command"]], Fore.RED)
            else:
                # Для других ошибок выводим ответ от модема
                self.print_table([[command, response]], Fore.RED)

        except Exception as e:
            logging.error(f"Ошибка при удалении файла: {e}")
            self.print_table([[command, f"Error: {e}"]], Fore.RED)



    def print_table(self, rows, color):
        """
        Print a formatted table with the specified color.

        :param rows: List of rows to print in the table.
        :param color: Color for the table output.
        """
        print(color + tabulate(rows, headers=["Message", "Details"], tablefmt="grid") + Style.RESET_ALL)
    
    def log_command_and_response(self, command, response):
        """Логирует команду и ответ с таймштампом в файл."""
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            with open(self.log_file, 'a') as log_file:
                log_file.write(f"{timestamp} - Command: {command}\n")
                if response:
                    log_file.write(f"{timestamp} - Response: {response}\n")
                else:
                    log_file.write(f"{timestamp} - Waiting for response...\n")
                log_file.write("\n")
        except Exception as e:
            logging.error(f"Ошибка при записи в лог: {e}")
if __name__ == "__main__":
    modem = Modem()
    modem.find_modem_port()

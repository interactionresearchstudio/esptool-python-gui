from esptool import main as esptool_main
import urllib.request
import json
import tempfile
import os
import serial
import sys
import glob
from kivy.app import App
import ssl
from threading import Thread

# Kivy imports
from kivy.uix.label import Label
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.core.window import Window

if not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None):
    ssl._create_default_https_context = ssl._create_unverified_context

github_api_url = 'https://api.github.com/repos/interactionresearchstudio/ESP32-SOCKETIO/releases'

esptool_options = ['--chip', 'esp32',
                   '--port', '/dev/cu.myserial',
                   '--baud', '921600',
                   '--before', 'default_reset',
                   '--after', 'hard_reset',
                   'write_flash', '-z', '--flash_mode', 'dio',
                   '--flash_freq', '80m',
                   '--flash_size', 'detect',
                   '0x0000', 'app.ino.bin'
                   ]

esptool_erase_options = ['--chip', 'esp32',
                         '--port', '/dev/cu.myserial',
                         '--baud', '921600',
                         '--before', 'default_reset',
                         '--after', 'no_reset',
                         'erase_flash'
                         ]


class EspToolManager(Thread):
    def __init__(self, runnable, callback, port=None):
        Thread.__init__(self)
        self.runnable = runnable
        self.callback = callback
        self.port = port
        self.daemon = True

    def run(self):
        if self.port is None:
            self.runnable(self)
        else:
            self.runnable(self, self.port)

    # Get bin download url based on GitHub API URL
    @staticmethod
    def get_bin_url(api_url):
        try:
            with urllib.request.urlopen(api_url) as url:
                data = json.loads(url.read().decode())
                print(data[0])
                return data[0]['assets'][0]['browser_download_url']
        except Exception as e:
            print(e)
            return None

    # Wipe device flash
    def erase_flash(self, serial_port):
        # Write to device with esptool
        esptool_erase_options[3] = serial_port
        try:
            esptool_main(esptool_erase_options)
            self.callback(0)
            # return True
        except Exception as e:
            print(e)
            self.callback(1)
            # return e

    @staticmethod
    def serial_ports():
        """ Lists serial port names

            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        if sys.platform.startswith('win'):
            print("win")
            ports = ['COM%s' % (i + 1) for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            # this excludes your current terminal "/dev/tty"
            print("linux")
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            print("mac")
            ports = glob.glob('/dev/cu.*')
        else:
            raise EnvironmentError('Unsupported platform')

        result = []
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except (OSError, serial.SerialException):
                pass
        return result

    @staticmethod
    def get_bin_file(bin_url):
        try:
            with urllib.request.urlopen(bin_url) as response:
                data = response.read()
                with tempfile.NamedTemporaryFile(delete=False) as fp:
                    fp.write(data)
                    fp.close()
                    return fp
        except Exception as e:
            print(e)
            return None

    # Upload bin file from GitHub to device
    def upload_from_github(self, serial_port):
        # Get bin file URL from GitHub
        bin_url = self.get_bin_url(github_api_url)
        if bin_url is None:
            print("Error finding firmware!")
            self.callback(1)
            # return 1

        # Download bin file and save temporarily
        fp = self.get_bin_file(bin_url)
        if fp is None:
            print("Error downloading firmware!")
            self.callback(2)
            # return 2

        # Write to device with esptool
        esptool_options[3] = serial_port
        esptool_erase_options[3] = serial_port
        esptool_options[-1] = fp.name
        try:
            esptool_main(esptool_options)
            os.unlink(fp.name)
            self.callback(0)
            # return 0
        except Exception as e:
            os.unlink(fp.name)
            print(e)
            self.callback(3)
            # return 3

    # Update serial list dropdown
    def get_serial_list(self):
        print("Update serial list")
        new_list = self.serial_ports()
        self.callback(new_list)
        # return new_list


class MainPage(GridLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_port = " "

        self.cols = 1
        self.padding = 40
        self.spacing = (0, 100)

        # Title
        self.add_widget(Label(text="[b]IRS Firmware Uploader[/b]", font_size='20sp', markup=True))

        # Status label
        self.status_label = Label(text="Idle", markup=True)
        self.add_widget(self.status_label)

        # Dropdown
        self.serial_dropdown = DropDown()
        self.dropdown_button = Button(text="Select Serial Port")
        self.dropdown_button.bind(on_release=self.serial_dropdown.open)
        self.serial_dropdown.bind(on_select=lambda instance, x: setattr(self.dropdown_button, 'text', x))
        self.add_widget(self.dropdown_button)

        # Refresh serial ports
        self.refresh_serial_ports_button = Button(text="Refresh Serial Ports")
        self.refresh_serial_ports_button.bind(on_release=lambda instance: self.get_serial_list())
        self.add_widget(self.refresh_serial_ports_button)

        # Upload button
        self.upload_button = Button(text="Upload Firmware", background_color=[66/255, 245/255, 129/255, 1])
        self.upload_button.bind(on_release=lambda btn: self.upload_firmware())
        self.add_widget(self.upload_button)

        # Erase button
        self.erase_button = Button(text="Wipe Device")
        self.erase_button.bind(on_release=lambda btn: self.erase_device())
        self.add_widget(self.erase_button)

        self.get_serial_list()

        Window.size = (400, 600)

    def select_port(self, port):
        self.current_port = port
        self.serial_dropdown.select(port)

    def get_serial_list(self):
        self.refresh_serial_ports_button.disabled = True
        thread = EspToolManager(EspToolManager.get_serial_list, self.on_serial_update)
        thread.start()

    def on_serial_update(self, serial_list):
        self.serial_dropdown.clear_widgets()
        for port in serial_list:
            btn = Button(text=port, size_hint_y=None, height=60)
            btn.bind(on_release=lambda _btn: self.select_port(_btn.text))
            self.serial_dropdown.add_widget(btn)
        self.refresh_serial_ports_button.disabled = False

    def upload_firmware(self):
        self.upload_button.disabled = True
        setattr(self.status_label, 'text', 'Uploading firmware...')
        thread = EspToolManager(EspToolManager.upload_from_github, self.on_upload_exit, port=self.current_port)
        thread.start()

    def erase_device(self):
        self.erase_button.disabled = True
        setattr(self.status_label, 'text', 'Uploading firmware...')
        thread = EspToolManager(EspToolManager.erase_flash, self.on_upload_exit, port=self.current_port)
        thread.start()

    def on_upload_exit(self, result):
        if result == 0:
            setattr(self.status_label, 'text', '[color=00ff00]Success![/color]')
            print('Success')
        elif result == 1:
            setattr(self.status_label, 'text', '[color=ff0000]Error finding firmware![/color]')
            print('Error finding firmware')
        elif result == 2:
            setattr(self.status_label, 'text', '[color=ff0000]Error downloading firmware![/color]')
            print('Error downloading firmware')
        elif result == 3:
            setattr(self.status_label, 'text', '[color=ff0000]Error uploading to device![/color]')
            print('Error uploading to device')
        elif result == 4:
            setattr(self.status_label, 'text', '[color=ff0000]Error erasing device![/color]')
            setattr(self.status_label, 'text', 'Error erasing device!')
            print('Error erasing device')
        self.erase_button.disabled = False
        self.upload_button.disabled = False


class IrsFirmwareUploader(App):
    def build(self):
        return MainPage()


if __name__ == "__main__":
    irs_firmware_uploader = IrsFirmwareUploader()
    irs_firmware_uploader.run()

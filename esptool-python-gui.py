from esptool import main as esptool_main
import urllib.request
import json
import tempfile
import os
import serial
import sys
import glob
import ssl
from threading import Thread
import wx


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


class AppFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super(AppFrame, self).__init__(*args, **kw)
        pnl = wx.Panel(self)

        # put some text with a larger bold font on it
        st = wx.StaticText(pnl, label="IRS Firmware Uploader")
        font = st.GetFont()
        font.PointSize += 10
        font = font.Bold()
        st.SetFont(font)

        # and create a sizer to manage the layout of child widgets
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(st, wx.SizerFlags().Border(wx.TOP | wx.LEFT, 25))
        pnl.SetSizer(sizer)

        # and a status bar
        self.CreateStatusBar()
        self.SetStatusText("Idle")

    def OnExit(self, event):
        """Close the frame, terminating the application."""
        self.Close(True)


if __name__ == '__main__':
    app = wx.App()
    frm = AppFrame(None, title='IRS Firmware Uploader')
    frm.Show()
    app.MainLoop()

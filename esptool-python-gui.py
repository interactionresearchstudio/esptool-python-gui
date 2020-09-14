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
server_projects_url = 'https://irs-socket-server-staging.herokuapp.com/projects'

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
    def __init__(self, runnable, callback, port=None, erase=False, url=None):
        Thread.__init__(self)
        self.runnable = runnable
        self.callback = callback
        self.port = port
        self.url = url
        self.daemon = True
        self.erase = erase

    def run(self):
        if self.port is None:
            self.runnable(self)
        else:
            self.runnable(self, self.port, self.url)

    # Get bin download url based on GitHub API URL
    @staticmethod
    def get_bin_url(api_url):
        try:
            with urllib.request.urlopen(api_url) as url:
                data = json.loads(url.read().decode())
                bin_url = None
                for asset in data[0]['assets']:
                    if asset['name'] == 'app-combined.bin':
                        bin_url = asset['browser_download_url']
                        print(bin_url)
                        return bin_url
                print('Error: No app-combined.bin in release.')
                return bin_url
        except Exception as e:
            print(e)
            return None

    # Get bin download url based on GitHub API URL
    @staticmethod
    def get_projects():
        try:
            with urllib.request.urlopen(server_projects_url) as url:
                data = json.loads(url.read().decode())
                return data['projects']
        except Exception as e:
            print(e)
            return None

    @staticmethod
    def serial_ports():
        """ Lists serial port names

            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        if sys.platform.startswith('win'):
            ports = ['COM%s' % (i + 1) for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            # this excludes your current terminal "/dev/tty"
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
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
    def upload_from_github(self, serial_port, url):
        # Get bin file URL from GitHub
        bin_url = self.get_bin_url(url)
        if bin_url is None:
            print("Error finding firmware!")
            self.callback(1)

        # Download bin file and save temporarily
        fp = self.get_bin_file(bin_url)
        if fp is None:
            print("Error downloading firmware!")
            self.callback(2)

        # Write to device with esptool
        esptool_options[3] = serial_port
        esptool_erase_options[3] = serial_port
        esptool_options[-1] = fp.name
        try:
            if self.erase:
                esptool_main(esptool_erase_options)
            esptool_main(esptool_options)
            os.unlink(fp.name)
            self.callback(0)
        except Exception as e:
            os.unlink(fp.name)
            print("Error uploading to device!")
            print(e)
            self.callback(3)

    # Update serial list dropdown
    def get_serial_list(self):
        new_list = self.serial_ports()
        self.callback(new_list)

    def get_projects_list(self):
        new_list = self.get_projects()
        self.callback(new_list)


class RedirectText:
    def __init__(self, text_ctrl):
        self.__out = text_ctrl

    def write(self, string):
        if string.startswith("\r"):
            # carriage return -> remove last line i.e. reset position to start of last line
            current_value = self.__out.GetValue()
            last_newline = current_value.rfind("\n")
            new_value = current_value[:last_newline + 1]  # preserve \n
            new_value += string[1:]  # chop off leading \r
            wx.CallAfter(self.__out.SetValue, new_value)
        else:
            wx.CallAfter(self.__out.AppendText, string)

    # noinspection PyMethodMayBeStatic
    def flush(self):
        # noinspection PyStatementEffect
        None


class MainFrame(wx.Frame):

    def __init__(self, parent):
        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title="Yo-Yo Machines", pos=wx.DefaultPosition,
                          size=wx.Size(486, 504), style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)

        self.current_serial = ""
        self.current_project_url = ""
        self.erase_flash = False

        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)

        root_sizer = wx.BoxSizer(wx.VERTICAL)

        self.title_label = wx.StaticText(self, wx.ID_ANY, u"Yo-Yo Machines Firmware Uploader", wx.DefaultPosition,
                                         wx.DefaultSize, 0)
        self.title_label.Wrap(-1)

        root_sizer.Add(self.title_label, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        self.static_line = wx.StaticLine(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, wx.LI_HORIZONTAL)
        root_sizer.Add(self.static_line, 0, wx.ALL | wx.EXPAND, 5)

        flexgrid_sizer = wx.FlexGridSizer(4, 2, 0, 0)
        flexgrid_sizer.AddGrowableCol(1)
        flexgrid_sizer.AddGrowableRow(2)
        flexgrid_sizer.SetFlexibleDirection(wx.BOTH)
        flexgrid_sizer.SetNonFlexibleGrowMode(wx.FLEX_GROWMODE_SPECIFIED)

        self.serial_label = wx.StaticText(self, wx.ID_ANY, u"Device", wx.DefaultPosition, wx.DefaultSize, 0)
        self.serial_label.Wrap(-1)

        flexgrid_sizer.Add(self.serial_label, 0, wx.ALL, 5)

        serial_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.serial_list = []
        self.serial_choice = wx.Choice(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, self.serial_list, 0)
        self.serial_choice.SetSelection(0)
        serial_sizer.Add(self.serial_choice, 1, wx.ALL, 5)

        self.serial_refresh_button = wx.Button(self, wx.ID_ANY, u"Refresh List", wx.DefaultPosition, wx.DefaultSize, 0)
        serial_sizer.Add(self.serial_refresh_button, 0, wx.ALL, 5)

        flexgrid_sizer.Add(serial_sizer, 1, wx.EXPAND, 5)

        self.projects_label = wx.StaticText(self, wx.ID_ANY, u"Project", wx.DefaultPosition, wx.DefaultSize, 0)
        self.projects_label.Wrap(-1)

        flexgrid_sizer.Add(self.projects_label, 0, wx.ALL, 5)

        self.projects_list = []
        self.projects_choice = wx.Choice(self, wx.ID_ANY, wx.DefaultPosition, wx.DefaultSize, self.projects_list, 0)
        self.projects_choice.SetSelection(0)
        flexgrid_sizer.Add(self.projects_choice, 0, wx.ALL | wx.EXPAND, 5)

        self.erase_label = wx.StaticText(self, wx.ID_ANY, u"Erase WiFi Details", wx.DefaultPosition, wx.DefaultSize, 0)
        self.erase_label.Wrap(-1)

        flexgrid_sizer.Add(self.erase_label, 0, wx.ALL, 5)

        self.erase_checkbox = wx.CheckBox(self, wx.ID_ANY,
                                          u"Yes, erase WiFi details on the device.",
                                          wx.DefaultPosition,
                                          wx.DefaultSize, 0)
        flexgrid_sizer.Add(self.erase_checkbox, 0, wx.ALL, 5)

        flexgrid_sizer.Add((0, 0), 1, wx.EXPAND, 5)

        self.upload_button = wx.Button(self, wx.ID_ANY, u"Upload", wx.DefaultPosition, wx.DefaultSize, 0)

        self.upload_button.SetDefault()
        flexgrid_sizer.Add(self.upload_button, 0, wx.ALL | wx.EXPAND, 5)

        root_sizer.Add(flexgrid_sizer, 0, wx.EXPAND, 5)

        self.console_text = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString, wx.DefaultPosition, wx.DefaultSize,
                                        wx.HSCROLL | wx.TE_MULTILINE | wx.TE_READONLY)
        root_sizer.Add(self.console_text, 1, wx.ALL | wx.EXPAND, 5)

        self.SetSizer(root_sizer)
        self.Layout()
        self.status_bar = self.CreateStatusBar(1, wx.STB_SIZEGRIP, wx.ID_ANY)

        self.Centre(wx.BOTH)

        sys.stdout = RedirectText(self.console_text)

        self.status_bar.SetStatusText("Idle")

        # Connect Events
        self.serial_choice.Bind(wx.EVT_CHOICE, self.on_serial_choice)
        self.serial_refresh_button.Bind(wx.EVT_BUTTON, self.on_serial_refresh)
        self.projects_choice.Bind(wx.EVT_CHOICE, self.on_projects_choice)
        self.erase_checkbox.Bind(wx.EVT_CHECKBOX, self.on_checkbox)
        self.upload_button.Bind(wx.EVT_BUTTON, self.on_upload_click)

        self.update_serial_list()
        self.update_projects_list()

    def __del__(self):
        pass

    def populate_serial_list(self, new_list):
        self.serial_list = new_list
        self.serial_choice.Clear()
        self.serial_choice.AppendItems(self.serial_list)
        self.current_serial = self.serial_list[0]

    def populate_projects_list(self, new_list):
        self.projects_list = new_list
        project_names = []
        for item in self.projects_list:
            project_names.append(item['name'])
        self.projects_choice.Clear()
        self.projects_choice.AppendItems(project_names)
        self.current_project_url = self.projects_list[0]['releaseUrl']

    def update_status(self, result):
        if result == 0:
            self.status_bar.SetStatusText("Success!")
            wx.CallAfter(self.console_text.AppendText, "Success!")
        elif result == 1:
            self.status_bar.SetStatusText("Error finding firmware!")
            wx.CallAfter(self.console_text.AppendText, "Error finding firmware!")
        elif result == 2:
            self.status_bar.SetStatusText("Error downloading firmware!")
            wx.CallAfter(self.console_text.AppendText, "Error downloading firmware!")
        elif result == 3:
            self.status_bar.SetStatusText("Error uploading to device!")
            wx.CallAfter(self.console_text.AppendText, "Error uploading to device!")
        elif result == 4:
            self.status_bar.SetStatusText("Error erasing data!")
            wx.CallAfter(self.console_text.AppendText, "Error erasing data!")
        self.upload_button.Enable()

    def upload_firmware(self):
        self.console_text.SetValue("")
        self.status_bar.SetStatusText("Uploading firmware...")
        wx.CallAfter(self.console_text.AppendText, "Uploading firmware...")
        thread = EspToolManager(EspToolManager.upload_from_github,
                                lambda res: self.update_status(res),
                                port=self.current_serial, erase=self.erase_flash, url=self.current_project_url)
        thread.start()

    def update_serial_list(self):
        thread = EspToolManager(EspToolManager.get_serial_list, lambda new_list: self.populate_serial_list(new_list))
        thread.start()

    def update_projects_list(self):
        thread = EspToolManager(EspToolManager.get_projects_list,
                                lambda new_list: self.populate_projects_list(new_list))
        thread.start()

    # Event handlers
    def on_serial_refresh(self, event):
        self.update_serial_list()
        event.Skip()

    def on_projects_choice(self, event):
        choice = event.GetEventObject()
        for project in self.projects_list:
            if project['name'] == choice:
                self.current_project_url = project['releaseUrl']

    def on_serial_choice(self, event):
        choice = event.GetEventObject()
        self.current_serial = choice.GetString(choice.GetSelection())

    def on_checkbox(self, event):
        checkbox = event.GetEventObject()
        self.erase_flash = checkbox.GetValue()

    def on_upload_click(self, event):
        self.upload_button.Disable()
        self.upload_firmware()
        event.Skip()


if __name__ == '__main__':
    app = wx.App()
    frm = MainFrame(None)
    frm.Show()
    app.MainLoop()

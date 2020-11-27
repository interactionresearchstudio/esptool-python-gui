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
import atexit

if not os.environ.get('PYTHONHTTPSVERIFY', '') and getattr(ssl, '_create_unverified_context', None):
    ssl._create_default_https_context = ssl._create_unverified_context

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


class SerialPrinter(Thread):
    def __init__(self, port):
        Thread.__init__(self)
        self.serial = serial.Serial(port)
        self.serial.baudrate = 115200
        self.serial.flushInput()
        self.is_running = True
        print("Started debug.")

    def run(self):
        while self.is_running:
            try:
                serial_in = self.serial.readline().strip()
                try:
                    serial_decoded = serial_in.decode('ascii')
                    serial_decoded.strip()
                except UnicodeDecodeError:
                    serial_decoded = ''
                print(serial_decoded)
            except serial.SerialException:
                continue

    def stop(self):
        self.serial.flushInput()
        self.is_running = False
        self.serial.close()
        print("Stopped debug.")


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
            ports = ['COM%s' % (i + 1) for i in range(32)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            # this excludes your current terminal "/dev/tty"
            ports = glob.glob('/dev/tty[A-Za-z]*')
        elif sys.platform.startswith('darwin'):
            ports = glob.glob('/dev/cu.*')
        else:
            raise EnvironmentError('Unsupported platform')

        result = []
        for port in ports:
            if sys.platform.startswith('win'):
                try:
                    s = serial.Serial(port)
                    s.close()
                    result.insert(0, port)
                except (OSError, serial.SerialException):
                    pass
            else:
                if 'cu.SLAB_USBtoUART' in port:
                    result.insert(0, port)
                else:
                    result.append(port)
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
            print(" ")
            print("👇 Please hold down BOOT button 👇")
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

    def upload_bin(self, serial_port, filename):
        # Write to device with esptool
        esptool_options[3] = serial_port
        esptool_erase_options[3] = serial_port
        esptool_options[-1] = filename
        try:
            print(" ")
            print("👇 Please hold down BOOT button 👇")
            if self.erase:
                esptool_main(esptool_erase_options)
            esptool_main(esptool_options)
            self.callback(0)
        except Exception as e:
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
        wx.CallAfter(self.__out.WriteText, string)

    # noinspection PyMethodMayBeStatic
    def flush(self):
        # noinspection PyStatementEffect
        None


class DropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        wx.FileDropTarget.__init__(self)
        self.frame = frame

    def OnDropFiles(self, x, y, filenames):
        self.frame.on_file_drop(filenames)
        return True


class MainFrame(wx.Frame):

    def __init__(self, parent):
        wx.Frame.__init__(self, parent, id=wx.ID_ANY, title="Yo-Yo Firmware Uploader", pos=wx.DefaultPosition,
                          size=wx.Size(486, 504), style=wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL)

        # Clean quit handlers
        self.Bind(wx.EVT_CLOSE, self.on_exit)
        atexit.register(lambda: self.on_exit(None))
        self.is_exiting = False
        self.Bind(wx.EVT_MENU, self.on_exit)
        accel_tbl = wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('Q'), wx.ID_ANY)])
        self.SetAcceleratorTable(accel_tbl)

        self.current_serial = ""
        self.current_project_url = ""
        self.erase_flash = False
        self.serial_thread = None
        self.esptool_thread = None

        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)

        menu_bar = wx.MenuBar()
        self.SetMenuBar(menu_bar)

        # Drag and drop
        file_drop_target = DropTarget(self)
        self.SetDropTarget(file_drop_target)

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

        upload_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.upload_button = wx.Button(self, wx.ID_ANY, u"Upload", wx.DefaultPosition, wx.DefaultSize, 0)
        self.upload_button.SetDefault()
        upload_sizer.Add(self.upload_button, 1, wx.ALL, 5)

        self.debug_button = wx.Button(self, wx.ID_ANY, u"Start Debug", wx.DefaultPosition, wx.DefaultSize, 0)
        upload_sizer.Add(self.debug_button, 0, wx.ALL, 5)

        flexgrid_sizer.Add(upload_sizer, 1, wx.EXPAND, 5)

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
        self.debug_button.Bind(wx.EVT_BUTTON, self.on_debug_click)

        print("Refreshing serial list...")
        self.update_serial_list()
        self.update_projects_list()

    def __del__(self):
        pass

    def handle_key(self, event):
        print("Key pressed!")
        if event.GetKeyCode() == 'q' and event.GetModifiers() == wx.MOD_CONTROL:
            self.on_exit(None)

    def exit_gracefully(self):
        if self.is_exiting is False:
            self.is_exiting = True
            print("Exiting...")
            if self.esptool_thread is not None:
                print("Stopping esptool thread...")
                self.esptool_thread.join()
            if self.serial_thread is not None:
                print("Stopping serial thread...")
                self.serial_thread.stop()
                self.serial_thread.join()
            self.Close()
            exit()

    def on_exit(self, e):
        self.exit_gracefully()
        if e is not None:
            e.Skip()

    def populate_serial_list(self, new_list):
        self.serial_list = new_list
        self.serial_choice.Clear()
        self.serial_choice.AppendItems(self.serial_list)
        self.current_serial = self.serial_list[0]
        print('Refreshed serial list')
        self.serial_refresh_button.Enable()

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
        self.debug_button.Enable()
        self.serial_refresh_button.Enable()
        self.serial_choice.Enable()
        try:
            self.esptool_thread.join()
            self.esptool_thread = None
        except RuntimeError:
            self.esptool_thread = None

    def upload_firmware(self):
        self.console_text.SetValue("")
        self.status_bar.SetStatusText("Uploading firmware...")
        wx.CallAfter(self.console_text.AppendText, "Uploading firmware...")
        self.esptool_thread = EspToolManager(EspToolManager.upload_from_github,
                                             lambda res: self.update_status(res),
                                             port=self.current_serial, erase=self.erase_flash,
                                             url=self.current_project_url)
        self.esptool_thread.start()

    def upload_bin_file(self, filename):
        self.console_text.SetValue("")
        self.status_bar.SetStatusText("Uploading firmware...")
        wx.CallAfter(self.console_text.AppendText, "Uploading firmware...")

        self.esptool_thread = EspToolManager(EspToolManager.upload_bin,
                                             lambda res: self.update_status(res),
                                             port=self.current_serial, erase=self.erase_flash,
                                             url=filename)
        self.esptool_thread.start()

    def update_serial_list(self):
        self.esptool_thread = EspToolManager(EspToolManager.get_serial_list,
                                             lambda new_list: self.populate_serial_list(new_list))
        self.esptool_thread.start()
        self.serial_refresh_button.Disable()

    def update_projects_list(self):
        self.esptool_thread = EspToolManager(EspToolManager.get_projects_list,
                                             lambda new_list: self.populate_projects_list(new_list))
        self.esptool_thread.start()

    # Event handlers
    def on_serial_refresh(self, event):
        print('Refreshing serial list...')
        self.update_serial_list()
        event.Skip()

    def on_projects_choice(self, event):
        choice = event.GetEventObject()
        for project in self.projects_list:
            if project['name'] == choice.GetString(choice.GetSelection()):
                self.current_project_url = project['releaseUrl']

    def on_serial_choice(self, event):
        choice = event.GetEventObject()
        self.current_serial = choice.GetString(choice.GetSelection())

    def on_checkbox(self, event):
        checkbox = event.GetEventObject()
        self.erase_flash = checkbox.GetValue()

    def on_upload_click(self, event):
        if self.serial_thread is not None:
            self.debug_button.SetLabelText("Start Debug")
            self.serial_thread.stop()
            self.status_bar.SetStatusText("Idle")
            self.serial_thread.join()
            self.serial_thread = None
            self.serial_refresh_button.Enable()
        self.upload_button.Disable()
        self.debug_button.Disable()
        self.serial_choice.Disable()
        self.serial_refresh_button.Disable()
        self.upload_firmware()
        event.Skip()

    def on_debug_click(self, event):
        if self.serial_thread is not None:
            self.debug_button.SetLabelText("Start Debug")
            self.serial_thread.stop()
            self.status_bar.SetStatusText("Idle")
            self.serial_thread.join()
            self.serial_thread = None
            self.serial_refresh_button.Enable()
            self.serial_choice.Enable()
        else:
            self.debug_button.SetLabelText("Stop Debug")
            self.serial_thread = SerialPrinter(self.current_serial)
            self.serial_thread.start()
            self.status_bar.SetStatusText("Debugging")
            self.serial_refresh_button.Disable()
            self.serial_choice.Disable()
        event.Skip()

    def on_file_drop(self, filenames):
        for f in filenames:
            if f.endswith('combined.bin'):
                bin_file = f
                print("Uploading bin file...")
                self.upload_bin_file(bin_file)
                return
        print("Not a bin file! Will not upload.")


if __name__ == '__main__':
    app = wx.App()
    frm = MainFrame(None)
    frm.Show()
    app.MainLoop()

from esptool import main as esptool_main
import urllib.request
import json
import tempfile
import os
import serial
import sys
import glob
from tkinter import *
from tkinter import ttk

github_api_url = 'https://api.github.com/repos/interactionresearchstudio/ESP32-SOCKETIO/releases'

esptool_options = ['--chip', 'esp32',
'--port', '/dev/cu.myserial',
'--baud', '921600',
'--before', 'default_reset',
'--after', 'hard_reset',
'write_flash', '-z', '--flash_mode', 'dio',
'--flash_freq', '80m',
'--flash_size', 'detect',
'0x10000', 'app.ino.bin'
]

esptool_erase_options = ['--chip', 'esp32',
'--port', '/dev/cu.myserial',
'--baud', '921600',
'--before', 'default_reset',
'--after', 'no_reset',
'erase_flash'
]

print("Imported esptool.")

def get_bin_url(api_url):
    try:
        with urllib.request.urlopen(api_url) as url:
            data = json.loads(url.read().decode())
            print(data[0])
            return data[0]['assets'][0]['browser_download_url']
    except Exception as e:
        print(e)
        return None

def erase_flash(serial_port):
    upload_button.config(state=DISABLED)
    status_var.set("Downloading firmware...")
    result_label.config(fg="blue")

    # Write to device with esptool
    esptool_erase_options[3] = serial_port
    try:
        status_var.set("Erasing device...")
        window.update()
        esptool_main(esptool_erase_options)
        status_var.set("Device erased.")
        result_label.config(fg="green")
        upload_button.config(state=NORMAL)
    except Exception as e:
        status_var.set("Error erasing device!")
        result_label.config(fg="red")
        upload_button.config(state=NORMAL)
        os.unlink(fp.name)
        print(e)

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
        ports = glob.glob('/dev/tty.*')
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

def get_bin_file(bin_url):
    try:
        with urllib.request.urlopen(bin_url) as response:
            data = response.read()
            with tempfile.NamedTemporaryFile(delete=False) as fp:
                fp.write(data)
                fp.close()
                return fp
    except Exception as e:
        return None
        print(e)

def upload_from_github(serial_port):
    upload_button.config(state=DISABLED)
    status_var.set("Downloading firmware...")
    result_label.config(fg="blue")
    window.update()

    # Get bin file URL from GitHub
    bin_url = get_bin_url(github_api_url)
    if bin_url == None:
        status_var.set("Error finding firmware!")
        result_label.config(fg="red")
        upload_button.config(state=NORMAL)
        return

    # Download bin file and save temporarily
    fp = get_bin_file(bin_url)
    if fp == None:
        status_var.set("Error downloading firmware!")
        result_label.config(fg="red")
        upload_button.config(state=NORMAL)
        return

    # Write to device with esptool
    esptool_options[3] = serial_port
    esptool_erase_options[3] = serial_port
    esptool_options[-1] = fp.name
    try:
        status_var.set("Writing firmware...")
        window.update()
        esptool_main(esptool_options)
        os.unlink(fp.name)
        status_var.set("Success!")
        result_label.config(fg="green")
        upload_button.config(state=NORMAL)
    except Exception as e:
        status_var.set("Error writing firmware!")
        result_label.config(fg="red")
        upload_button.config(state=NORMAL)
        os.unlink(fp.name)
        print(e)


def update_serial_list():
    print("Update serial list")
    option.set('')
    opt.children['menu'].delete(0, 'end')
    new_list = serial_ports()
    for item in new_list:
        opt.children['menu'].add_command(label=item, command=lambda: option.set(item))
    option.set(new_list[0])


window = Tk()
window.geometry('300x300')
window.title("IRS Firmware Uploader")

style = ttk.Style()
style.map("C.TButton",
    foreground=[('pressed', 'blue'), ('active', 'blue')],
    background=[('pressed', '!disabled', 'grey'), ('active', 'white')])

instructions = Label(window, wraplength=200, justify="left", text="Please select the device from the dropdown menu. When you're ready to upload the firmware, click Upload Firmware!")
instructions.place(relx=0.5, y=50, anchor=CENTER)

status_var = StringVar(window)
status_var.set("Idle")
result_label = Label(window, textvariable=status_var, width=30, fg="blue")
result_label.place(relx=0.5, rely=0.8, anchor=CENTER)

option_list = serial_ports()
option = StringVar(window)
option.set(option_list[0])
opt = OptionMenu(window, option, *option_list)
opt.config(width=30, font=('Helvetica', 12), bg="black")
opt.pack()
opt.place(relx=0.5, rely=0.4, anchor=CENTER)

refresh_list_button = ttk.Button(window,
    text="Refresh device list",
    command=update_serial_list, style="C.TButton")
refresh_list_button.place(relx=0.5, rely=0.5, anchor=CENTER)

upload_button = ttk.Button(window, text="Erase Device",
    command=lambda: erase_flash(option.get()), style="C.TButton")
upload_button.place(relx=0.5, rely=0.6, anchor=CENTER)

upload_button = ttk.Button(window, text="Upload Firmware",
    command=lambda: upload_from_github(option.get()), style="C.TButton")
upload_button.place(relx=0.5, rely=0.9, anchor=CENTER)

window.mainloop()

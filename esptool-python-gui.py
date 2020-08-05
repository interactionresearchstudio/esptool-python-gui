from esptool import main as esptool_main
import PySimpleGUI as sg

options = ['--chip', 'esp32',
'--port', '/dev/cu.usbserial-01E5C374',
'--baud', '921600',
'--before', 'default_reset',
'--after', 'hard_reset',
'write_flash', '-z', '--flash_mode', 'dio',
'--flash_freq', '80m',
'--flash_size', 'detect',
'0xe000', 'boot_app0.bin',
'0x1000', 'bootloader_qio_80m.bin',
'0x10000', '/var/folders/_c/51n3qnzd01sfpdd6mfq8j_jm0000gn/T/arduino_build_969576/sketch_aug05a.ino.bin',
'0x8000', '/var/folders/_c/51n3qnzd01sfpdd6mfq8j_jm0000gn/T/arduino_build_969576/sketch_aug05a.ino.partitions.bin']

print("Imported esptool.")

layout = [  [sg.Text('Upload firmware')],
            [sg.Text('Idle    ', key='-OUTPUT-')],
            [sg.Button('GO')] ]

window = sg.Window("SCADS ESP flasher", layout)

while True:
    event, values = window.read()
    if values is not None:
        print(values)
    if event == 'GO':
        print("Pressed ok.")
        try:
            esptool_main(options)
            window['-OUTPUT-'].update("Success!")
        except:
            window['-OUTPUT-'].update("ERROR :(")
    elif event == sg.WIN_CLOSED:

        break
print("Bye.")
window.close()

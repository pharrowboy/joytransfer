#!/usr/bin/env python3

import os
import time
import argparse
import asyncio
import logging

from multiprocessing import Process
from multiprocessing import Queue

from joycontrol import utils
from joycontrol.controller import Controller
from joycontrol.memory import FlashMemory
from patch_joycontrol.protocol import controller_protocol_factory
from patch_joycontrol.server import create_hid_server


import pygame


from aioconsole import ainput

from joycontrol import logging_default as log, utils
from joycontrol.command_line_interface import ControllerCLI
from joycontrol.controller_state import ControllerState, button_push, button_update, stick_update

from joycontrol.protocol import controller_protocol_factory


logger = logging.getLogger(__name__)

"""Emulates Switch controller. Opens joycontrol.command_line_interface to send button commands and more.
While running the cli, call "help" for an explanation of available commands.
Usage:
    run_controller_cli.py <controller> [--device_id | -d  <bluetooth_adapter_id>]
                                       [--spi_flash <spi_flash_memory_file>]
                                       [--reconnect_bt_addr | -r <console_bluetooth_address>]
                                       [--log | -l <communication_log_file>]
    run_controller_cli.py -h | --help
Arguments:
    controller      Choose which controller to emulate. Either "JOYCON_R", "JOYCON_L" or "PRO_CONTROLLER"
Options:
    -d --device_id <bluetooth_adapter_id>   ID of the bluetooth adapter. Integer matching the digit in the hci* notation
                                            (e.g. hci0, hci1, ...) or Bluetooth mac address of the adapter in string
                                            notation (e.g. "FF:FF:FF:FF:FF:FF").
                                            Note: Selection of adapters may not work if the bluez "input" plugin is
                                            enabled.
    --spi_flash <spi_flash_memory_file>     Memory dump of a real Switch controller. Required for joystick emulation.
                                            Allows displaying of JoyCon colors.
                                            Memory dumps can be created using the dump_spi_flash.py script.
    -r --reconnect_bt_addr <console_bluetooth_address>  Previously connected Switch console Bluetooth address in string
                                                        notation (e.g. "FF:FF:FF:FF:FF:FF") for reconnection.
                                                        Does not require the "Change Grip/Order" menu to be opened,
    -l --log <communication_log_file>       Write hid communication (input reports and output reports) to a file.
"""

def init_relais():
    # todo: - button layout parsing from config file
    #       - basic GUI to show/generate config file + to start/stop the script

    pygame.init()
    pygame.joystick.init()
    joystick = pygame.joystick.Joystick(0)
    joystick.init()

    buttons = {
        'a': 1,
        'b': 0,
        'x': 3,
        'y': 2,
        'minus':    6,
        'plus':     7,
        'home':     8,
        #'capture':  ,
        'l':    4,
        'r':    5,
        'l_stick': 9,
        'r_stick': 10
    }   

    analogs = {
        'l_stick_analog': [0, 1], # [horizontal axis, vertical axis] for analog sticks
        'r_stick_analog': [3, 4],
        'zl':   [2, -0.5], # [axis, threshold] for analog axes to be converted to buttons
        'zr':   [5, -0.5],
    }

    hat_id = 0

    return buttons, analogs, hat_id

async def relais(controller_state):
    buttons, analogs, hat_id = init_relais()
    buttons = dict((val, key) for key, val in buttons.items())

    joystick = pygame.joystick.Joystick(0)
    joystick.init()
    skip = 0
    while True:
        skip += 1
        for event in pygame.event.get(): # User did something.
            if event.type == pygame.JOYBUTTONDOWN or event.type == pygame.JOYBUTTONUP:
                for button_id in list(buttons.keys()):        
                    val = joystick.get_button(button_id)
                    await button_update(controller_state, buttons[button_id], val)            
            
            # this is working but can get unresponsive if axes are moved to frequently (too many events in the queue to be processed fast)
            # I'll leave this commented out for better responsiveness in games like mario kart. 
            # If you want to use your xbox/playstation controller as a pro controller, consider using something like the 8bitdo adapters, you'll have more fun this way.

            #elif event.type == pygame.JOYAXISMOTION and skip%5 == 0:
            #    for key in analogs.keys():
            #        if key[-6:] == 'analog': # analog sticks 
            #            val_h = joystick.get_axis(analogs[key][0])                         
            #            val_v = joystick.get_axis(analogs[key][1])

            #            vals = {}
            #            vals['h'] = abs(int(((val_h + 1) / 2) * 4096) - 1) # converts to the range of [0, 4096) 
            #            vals['v'] = abs(int(((-1 * val_v + 1) / 2) * 4096) - 1) # converts to the range of [0, 4096) + inversion of the vertical axis
                                                                                # inversion might be an issue for other controllers...

             #           await stick_update(controller_state, key, vals)

             #       else: # analog triggers -> button conversion
             #           threshold = analogs[key][1]
             #           if joystick.get_axis(analogs[key][0]) > threshold:
             #               await button_update(controller_state, key, 1)
             #           else:
             #               await button_update(controller_state, key, 0)            

            elif event.type == pygame.JOYHATMOTION:
                hats = joystick.get_hat(hat_id)
                if hats[0] == 0: # left/right is unpressed 
                    await button_update(controller_state, 'left', 0)
                    await button_update(controller_state, 'right', 0)
                elif hats[0] == 1: # right is pressed
                    await button_update(controller_state, 'right', 1)
                elif hats[0] == -1: # left is pressed
                    await button_update(controller_state, 'left', 1)

                if hats[1] == 0: # up/down is unpressed
                    await button_update(controller_state, 'up', 0)
                    await button_update(controller_state, 'down', 0)
                elif hats[1] == 1: # up is pressed
                    await button_update(controller_state, 'up', 1)
                elif hats[1] == -1: # down is pressed
                    await button_update(controller_state, 'down', 1)

        time.sleep(0.001)

async def test_controller_buttons(controller_state: ControllerState):
   
    # Goto settings
    await button_push(controller_state, 'down', sec=1)
    await button_push(controller_state, 'right', sec=2)
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'left')
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # go all the way down
    await button_push(controller_state, 'down', sec=4)
    await asyncio.sleep(0.3)

    # goto "Controllers and Sensors" menu
    for _ in range(2):
        await button_push(controller_state, 'up')
        await asyncio.sleep(0.3)
    await button_push(controller_state, 'right')
    await asyncio.sleep(0.3)

    # go all the way down
    await button_push(controller_state, 'down', sec=3)
    await asyncio.sleep(0.3)

    # goto "Test Input Devices" menu
    await button_push(controller_state, 'up')
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # goto "Test Controller Buttons" menu
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # push all buttons except home and capture
    button_list = controller_state.button_state.get_available_buttons()
    if 'capture' in button_list:
        button_list.remove('capture')
    if 'home' in button_list:
        button_list.remove('home')

    user_input = asyncio.ensure_future(
        ainput(prompt='Pressing all buttons... Press <enter> to stop.')
    )

    # push all buttons consecutively until user input
    while not user_input.done():
        for button in button_list:
            await button_push(controller_state, button)
            await asyncio.sleep(0.1)

            if user_input.done():
                break

    # await future to trigger exceptions in case something went wrong
    await user_input

    # go back to home
    await button_push(controller_state, 'home')


async def set_amiibo(controller_state, file_path):
    """
    Sets nfc content of the controller state to contents of the given file.
    :param controller_state: Emulated controller state
    :param file_path: Path to amiibo dump file
    """
    loop = asyncio.get_event_loop()

    with open(file_path, 'rb') as amiibo_file:
        content = await loop.run_in_executor(None, amiibo_file.read)
        controller_state.set_nfc(content)


async def mash_button(controller_state, button, interval):
    # waits until controller is fully connected
    await controller_state.connect()

    if button not in controller_state.button_state.get_available_buttons():
        raise ValueError(f'Button {button} does not exist on {controller_state.get_controller()}')

    user_input = asyncio.ensure_future(
        ainput(prompt=f'Pressing the {button} button every {interval} seconds... Press <enter> to stop.')
    )
    # push a button repeatedly until user input
    while not user_input.done():
        await button_push(controller_state, button)
        await asyncio.sleep(float(interval))

    # await future to trigger exceptions in case something went wrong
    await user_input


async def _main2(args):

        # Create memory containing default controller stick calibration
    spi_flash = FlashMemory()

    # Get controller name to emulate from arguments
    controller = Controller.from_arg(args.controller)

    with utils.get_output(path=args.log, default=None) as capture_file:
        factory = controller_protocol_factory(controller, spi_flash=spi_flash)
        ctl_psm, itr_psm = 17, 19
        transport, protocol = await create_hid_server(factory, reconnect_bt_addr=args.reconnect_bt_addr,
                                                      ctl_psm=ctl_psm,
                                                      itr_psm=itr_psm, capture_file=capture_file,
                                                      device_id=args.device_id)

        controller_state = protocol.get_controller_state()

        await relais(controller_state)
        # Create command line interface and add some extra commands
        cli = ControllerCLI(controller_state)

        # Wrap the script so we can pass the controller state. The doc string will be printed when calling 'help'
        async def _run_test_controller_buttons():
            """
            test_buttons - Navigates to the "Test Controller Buttons" menu and presses all buttons.
            """
            await test_controller_buttons(controller_state)

        # add the script from above
        cli.add_command('test_buttons', _run_test_controller_buttons)

        # init_relais command
        async def _run_init_relais():
            """
            init_relais - init the relais and configure button layout
            """
            init_relais()

        # add the script from above
        cli.add_command('init_relais', _run_init_relais)

        # relais command
        async def _run_relais():
            """
            relais - run the relais
            """
            await relais(controller_state)

        # add the script from above
        cli.add_command('relais', _run_relais)

        # Mash a button command
        async def call_mash_button(*args):
            """
            mash - Mash a specified button at a set interval
            Usage:
                mash <button> <interval>
            """
            if not len(args) == 2:
                raise ValueError('"mash_button" command requires a button and interval as arguments!')

            button, interval = args
            await mash_button(controller_state, button, interval)

        # add the script from above
        cli.add_command('mash', call_mash_button)

        # Create amiibo command
        async def amiibo(*args):
            """
            amiibo - Sets nfc content
            Usage:
                amiibo <file_name>          Set controller state NFC content to file
                amiibo remove               Remove NFC content from controller state
            """
            if controller_state.get_controller() == Controller.JOYCON_L:
                raise ValueError('NFC content cannot be set for JOYCON_L')
            elif not args:
                raise ValueError('"amiibo" command requires file path to an nfc dump as argument!')
            elif args[0] == 'remove':
                controller_state.set_nfc(None)
                print('Removed nfc content.')
            else:
                await set_amiibo(controller_state, args[0])

        # add the script from above
        cli.add_command('amiibo', amiibo)

        try:
            await cli.run()
        finally:
            logger.info('Stopping communication...')
            await transport.close()

async def _main(args, c, q, reconnect_bt_addr=None):

    # Get controller name to emulate from arguments
    controller = Controller.PRO_CONTROLLER

    # prepare the the emulated controller
    factory = controller_protocol_factory(controller,
                            reconnect = reconnect_bt_addr)

    ctl_psm, itr_psm = 17, 19

    print('', end='\n' if c else ' ')
    print('  Joy Transfer  v0.1')
    print('INFO: Waiting for Switch to connect...', end='\n' if c else ' ')

    if c < 1:
        print('Please open the "Change Grip/Order" menu')

    transport, protocol, ns_addr = await create_hid_server(factory,
                                                  reconnect_bt_addr=reconnect_bt_addr,
                                                  ctl_psm=ctl_psm,
                                                  itr_psm=itr_psm,
                                                  unpair = not reconnect_bt_addr)
    controller_state = protocol.get_controller_state()

    # this is needed
    await controller_state.connect()

    if not reconnect_bt_addr:
        reconnect_bt_addr = ns_addr
        q.put(ns_addr)

    # wait back home in nintendo switch
    if c < 1:
        print('INFO: NINTENDO SWITCH', reconnect_bt_addr)
        if args.auto:
            controller_state.button_state.set_button('a', pushed=True)
            await controller_state.send()
        else:
            print('INFO: Press the button A or B or HOME')
        print()

        while 1:
            await asyncio.sleep(0.2)
    q.put('unlock') # unlock console
    print('hi :3')

    while 1:
        cmd = q.get() # wait command

        await test_button(controller_state, cmd)

'''
NINTENDO SWITCH
    - version 12.1.0
    - version 13.0.0
'''
async def test_button(ctrl, btn):
        available_buttons = ctrl.button_state.get_available_buttons()

        if btn == 'wake':
            # wake up control
            ctrl.button_state.clear()
            await ctrl.send()
            await asyncio.sleep(0.050) # stable minimum 0.050

        if btn not in available_buttons:
            return 1

        ctrl.button_state.set_button(btn, pushed=True)
        await ctrl.send()

        await asyncio.sleep(0.050) # stable minimum 0.050 press
        ctrl.button_state.set_button(btn, pushed=False)
        await ctrl.send()
        await asyncio.sleep(0.020) # stable minimum 0.020 release

        return 0

def handle_exception(loop, context):
    tasks = [t for t in asyncio.all_tasks() if t is not
                         asyncio.current_task()]
    for task in tasks:
        task.cancel()

count = 0

def test(args, c, q, b):
    try:
        loop.run_until_complete(
            _main(args, c, q, b)
        )
    except:
        pass

if __name__ == '__main__':

    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    parser = argparse.ArgumentParser()
    parser.add_argument('controller', help='JOYCON_R, JOYCON_L or PRO_CONTROLLER')
    parser.add_argument('--auto', dest='auto', action='store_true')
    parser.add_argument('-r', '--reconnect_bt_addr', type=str, default=None,
                        help='The Switch console Bluetooth address (or "auto" for automatic detection), for reconnecting as an already paired controller.')
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)

    queue = Queue()

   

    ns_addr = args.reconnect_bt_addr
    if ns_addr:
        count = 1

    for _ in range(2 - count):
        p = Process(target=test, args=(args, count, queue, ns_addr))
        p.start()

        if count < 1:
            ns_addr = queue.get() # wait nintendo switch address
            p.join()
        else:
            queue.get() # lock console

        while p.is_alive():
            
            loop.run_until_complete(_main2(args))
       

            
            

        # wait reconnection
        time.sleep(2) # important 2 or more
        count += 1

    print("bye")

#!/usr/bin/python3
import usb.core
import usb.util
import struct
import sys
import time
import argparse
import logging
import os
from pathlib import Path


log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(sys.stdout))

CMD_ID_EXIT = 0
CMD_ID_LIST = 1
CMD_ID_FILE_RANGE = 2

CMD_TYPE_REQUEST = 0
CMD_TYPE_RESPONSE = 1
CMD_TYPE_ACK = 2

BUFFER_SEGMENT_DATA_SIZE = 0x100000


class UsbContext:
    def __init__(self, vid: hex, pid: hex):
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev is None:
            raise ConnectionError(f'Device {vid}:{pid} not found')

        dev.reset()
        dev.set_configuration()
        cfg = dev.get_active_configuration()

        self._out = usb.util.find_descriptor(
            cfg[(0, 0)],
            custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
        self._in = usb.util.find_descriptor(
            cfg[(0, 0)],
            custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN
        )

        if self._out is None:
            raise LookupError(f'Device {vid}:{pid} output endpoint not found')
        if self._in is None:
            raise LookupError(f'Device {vid}:{pid} input endpoint not found')

    def read(self, data_size, timeout=0):
        return self._in.read(data_size, timeout=timeout)

    def write(self, data):
        self._out.write(data)


def process_file_range_command(data_size, context):
    log.info('File range')
    context.write(struct.pack('<4sIII', b'DBI0', CMD_TYPE_ACK, CMD_ID_FILE_RANGE, data_size))

    file_range_header = context.read(data_size)

    range_size = struct.unpack('<I', file_range_header[:4])[0]
    range_offset = struct.unpack('<Q', file_range_header[4:12])[0]
    nsp_name_len = struct.unpack('<I', file_range_header[12:16])[0]
    nsp_name = bytes(file_range_header[16:]).decode('utf-8')

    log.info(f'Range Size: {range_size}, Range Offset: {range_offset}, Name len: {nsp_name_len}, Name: {nsp_name}')

    response_bytes = struct.pack('<4sIII', b'DBI0', CMD_TYPE_RESPONSE, CMD_ID_FILE_RANGE, range_size)
    context.write(response_bytes)

    ack = bytes(context.read(16, timeout=0))
    cmd_type = struct.unpack('<I', ack[4:8])[0]
    cmd_id = struct.unpack('<I', ack[8:12])[0]
    data_size = struct.unpack('<I', ack[12:16])[0]
    log.debug(f'Cmd Type: {cmd_type}, Command id: {cmd_id}, Data size: {data_size}')
    log.debug('Ack')

    with open(nsp_name, 'rb') as f:
        f.seek(range_offset)

        curr_off = 0x0
        end_off = range_size
        read_size = BUFFER_SEGMENT_DATA_SIZE

        while curr_off < end_off:
            if curr_off + read_size >= end_off:
                read_size = end_off - curr_off

            buf = f.read(read_size)
            context.write(data=buf, timeout=0)
            curr_off += read_size


def poll_commands(context, work_dir_path):
    log.info('Entering command loop')
    while True:
        cmd_header = bytes(context.read(16, timeout=0))
        magic = cmd_header[:4]

        if magic != b'DBI0':  # Tinfoil USB Command 0
            continue

        cmd_type = struct.unpack('<I', cmd_header[4:8])[0]
        cmd_id = struct.unpack('<I', cmd_header[8:12])[0]
        data_size = struct.unpack('<I', cmd_header[12:16])[0]

        log.debug(f'Cmd Type: {cmd_type}, Command id: {cmd_id}, Data size: {data_size}')

        if cmd_id == CMD_ID_EXIT:
            process_exit_command(context)
        elif cmd_id == CMD_ID_FILE_RANGE:
            process_file_range_command(context, data_size)
        elif cmd_id == CMD_ID_LIST:
            process_list_command(context, work_dir_path)


def process_exit_command(context):
    log.info('Exit')
    context.write(struct.pack('<4sIII', b'DBI0', CMD_TYPE_RESPONSE, CMD_ID_EXIT, 0))
    sys.exit(0)


def process_list_command(context, work_dir_path):
    log.info('Get list')
    nsp_path_list = ""

    for dirName, subdirList, fileList in os.walk(work_dir_path):
        log.debug(f'Found directory: {dirName}')
        for filename in fileList:
            log.debug(f'\t{filename}')
            nsp_path_list += str(Path(dirName).joinpath(filename)) + '\n'
        
    nsp_path_list_bytes = nsp_path_list.encode('utf-8')
    nsp_path_list_len = len(nsp_path_list_bytes)

    context.write(struct.pack('<4sIII', b'DBI0', CMD_TYPE_RESPONSE, CMD_ID_LIST, nsp_path_list_len))

    ack = bytes(context.read(16, timeout=0))
    cmd_type = struct.unpack('<I', ack[4:8])[0]
    cmd_id = struct.unpack('<I', ack[8:12])[0]
    data_size = struct.unpack('<I', ack[12:16])[0]
    log.debug(f'Cmd Type: {cmd_type}, Command id: {cmd_id}, Data size: {data_size}')
    log.debug('Ack')

    context.write(nsp_path_list_bytes)


def connect_to_switch():
    while True:
        try:
            switch_context = UsbContext(vid=0x057E, pid=0x3000)
        except ConnectionError as e:
            log.info('Waiting for switch')
            time.sleep(1)
            continue
        return switch_context


def get_args(args):
    parser = argparse.ArgumentParser(
        prog='dbibackend',
        description='Install local titles into Nintendo switch via USB',
        add_help=False
    )
    parent_group = parser.add_argument_group(title='Command line params')
    parent_group.add_argument('--titles', '-t', default='.', type=str, required=False)
    parent_group.add_argument('--debug', action='store_true', default=False, required=False,
                              help='Enable debug output')
    return parser.parse_args(args)


def main():
    args = get_args(sys.argv[1:])

    if args.debug:
        log.setLevel(logging.DEBUG)

    if not Path(args.titles).is_dir():
        raise ValueError('Argument must be a directory')

    poll_commands(
        connect_to_switch(),
        work_dir_path=args.titles
    )


if __name__ == '__main__':
    main()

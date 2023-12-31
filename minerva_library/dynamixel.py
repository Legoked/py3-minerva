#!/usr/bin/python

# Copyright (c) 2016, Travis Deyle
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Georgia Tech Research Corporation nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED ''AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL GEORGIA
# TECH BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


#########################
# lib_robotis_v2.py
#########################

# This library is for controlling Robotis Dynamixel XM430 servos from python using a
# USB2Dyanmixel or other RS485 adaptor.  This library adheres to Dynamixel
# Communication protocol v2.0.

# [The original Georgia Tech lib_robots (eg. for controlling MX and EX servos)
#  used protocol v1.0. Hence the new library.]
#
# Sources:
# - https://github.com/gt-ros-pkg/hrl/blob/master/hrl_hardware_drivers/robotis/src/robotis/lib_robotis.py
# - http://support.robotis.com/en/product/dynamixel/x_series/xm430-w350.htm
# - http://support.robotis.com/en/product/dynamixel_pro/communication/instruction_status_packet.htm

import serial
import time
import thread
import sys, optparse
import math
import ipdb

def initial(c, POLYNOMIAL = 0x8005):
    # Adapted from StackOverflow implementation using the Robotis CRC table to
    # determine the polynomial. Sources:
    #  - http://stackoverflow.com/a/25259157
    #  - http://support.robotis.com/en/product/dynamixel_pro/communication/crc.htm
    crc = 0
    c = c << 8
    for j in range(8):
        if (crc ^ c) & 0x8000:
            crc = (crc << 1) ^ POLYNOMIAL
        else:
            crc = crc << 1
        c = c << 1
    return crc

tab = [ initial(i) & 0xffff for i in range(256) ]

def crc( ds ):
    if not isinstance(ds, str):
        Raise('Input must be a string')
    crc = 0x0000
    for i in ds:
        cc = 0xff & (ord(i)&0xff)
        tmp = (crc >> 8) ^ cc
        crc = (crc << 8) ^ tab[tmp & 0xff]
        crc = crc & 0xffff

    return crc


class USB2Dynamixel_Device():
    ''' Class that manages serial port contention between servos on same bus
    '''
    def __init__( self, dev_name = 'COM7', baudrate = 57600 ):
        try:
            self.dev_name = string.atoi( dev_name ) # stores the serial port as 0-based integer for Windows
        except:
            self.dev_name = dev_name # stores it as a /dev-mapped string for Linux / Mac

        self.mutex = thread.allocate_lock()
        self.servo_dev = None

        self.acq_mutex()
        self._open_serial( baudrate )
        self.rel_mutex()

    def acq_mutex(self):
        self.mutex.acquire()

    def rel_mutex(self):
        self.mutex.release()

    def send_serial(self, msg):
        # It is up to the caller to acquire / release mutex
        self.servo_dev.write( msg )

    def read_serial(self, nBytes=1):
        # It is up to the caller to acquire / release mutex
        rep = self.servo_dev.read( nBytes )
        return rep

    def _open_serial(self, baudrate):
        try:
            self.servo_dev = serial.Serial(self.dev_name, baudrate, timeout=1.0)
            # Closing the device first seems to prevent "Access Denied" errors on WinXP
            # (Conversations with Brian Wu @ MIT on 6/23/2010)
            self.servo_dev.close()
            self.servo_dev.setParity('N')
            self.servo_dev.setStopbits(1)
            self.servo_dev.open()

            self.servo_dev.flushOutput()
            self.servo_dev.flushInput()

        except (serial.serialutil.SerialException), e:
            raise RuntimeError('lib_robotis: Serial port not found!\n')
        if(self.servo_dev == None):
            raise RuntimeError('lib_robotis: Serial port not found!\n')





class Robotis_Servo2():
    ''' Class to use a robotis XM430 servo.
    '''
    def __init__(self, USB2Dynamixel, servo_id, series = None ):
        ''' USB2Dynamixel - USB2Dynamixel_Device object to handle serial port.
                            Handles threadsafe operation for multiple servos
            servo_id - servo ids connected to USB2Dynamixel 1,2,3,4 ... (1 to 253)
                       [0 is broadcast if memory serves]
            series - To load series-specific defaults. XM is only series supported by lib_robotis_v2.py
                     Any of the defaults can be overloaded
                     on a servo-by-servo bases in servo_config.py
        '''

        if series != 'XM':
            raise RuntimeError( 'Library only tested with XM series servos. Use at your discretion.' )

        self.settings = {
            'home_encoder': 0x7FF,
            'max_encoder': 0xFFF,
            'rad_per_enc': math.radians(360.0) / 0xFFF,
            'max_ang': math.radians(180),
            'min_ang': math.radians(-180),
            'flipped': False,
            'max_speed': math.radians(100),
        }

        # Error Checking
        if USB2Dynamixel == None:
            raise RuntimeError('lib_robotis: Robotis Servo requires USB2Dynamixel!\n')
        else:
            self.dyn = USB2Dynamixel

        # TODO: Replace this functionality
        # # ID exists on bus?
        self.servo_id = servo_id
        try:
            self.protocol2_read_address( 0x07 )
        except:
            raise RuntimeError('lib_robotis: Error encountered.  Could not find ID (%d) on bus (%s), or USB2Dynamixel 3-way switch in wrong position.\n' %
                               ( servo_id, self.dyn.dev_name ))

        '''
        # Set various parameters.  Load from servo_config.
        try:
            import servo_config as sc
            if sc.servo_param.has_key( self.servo_id ):
                self.settings.update( sc.servo_param[ self.servo_id ])
                print 'Loaded servo_config.py parameters.'
            else:
                print 'Warning: Servo id not found in servo_config.py.  Using defaults.'
        except:
            print 'Warning: servo_config.py not found.  Using defaults.'
        '''


    def init_cont_turn(self):
        raise NotImplementedError

    def kill_cont_turn(self):
        raise NotImplementedError

    def is_moving(self):
        ''' returns True if servo is moving.
        '''
        data = self.protocol2_read_address( 122, 1 )
        return data[0] != 0

    def read_voltage(self):
        raise NotImplementedError

    def read_temperature(self):
        raise NotImplementedError

    def read_load(self):
        raise NotImplementedError

    def read_encoder(self):
        raise NotImplementedError

    def read_angle(self):
        raise NotImplementedError

    def move_to_encoder(self, n):
        ''' move to encoder position n
        '''
        # In some border cases, we can end up above/below the encoder limits.
        #   eg. int(round(math.radians( 180 ) / ( math.radians(360) / 0xFFF ))) + 0x7FF => -1
        n = min( max( n, 0 ), self.settings['max_encoder'] )
        hi,lo = n / 256, n % 256
        return self.protocol2_write_address( 116, [lo, hi, 0, 0] )

    def move_angle(self, ang, angvel=None, blocking=True):
        ''' move to angle (radians)
        '''
        if angvel is not None:
            raise NotImplementedError('Angvel no longer supported.')

        if ang > self.settings['max_ang'] or ang < self.settings['min_ang']:
            print 'lib_robotis.move_angle: angle out of range- ', math.degrees(ang)
            print 'lib_robotis.ignoring move command.'
            return
        if self.settings['flipped']:
            ang = ang * -1.0
        enc_tics = int(round( ang / self.settings['rad_per_enc'] ))
        enc_tics += self.settings['home_encoder']
        self.move_to_encoder( enc_tics )

        #ipdb.set_trace()

        if blocking == True:
            while(self.is_moving()):
                continue

    def enable_torque(self):
        return self.protocol2_write_address( 64, [1])

    def disable_torque(self):
        return self.protocol2_write_address( 64, [0])

    def torque_mode(self):
        self.disable_torque()
        self.set_torque( 0 )
        self.protocol2_write_address( 11, [0] )
        self.enable_torque()

    def set_torque( self, val ):
        self.protocol2_write_address( 102, [ val & 0xff, (val<<8) & 0xff ])

    def read_torque( self ):
        params = self.protocol2_read_address( 126, 2 )
        return (params[1] << 8) + params[0]

    def set_angvel(self, angvel):
        raise NotImplementedError('No longer implmented, even for older servos; now uses PID params')

    def write_id(self, id):
        ''' changes the servo id (will turn off torque!)
        '''
        # Torque must be disabled to turn off EEPROM lock
        self.disable_torque()
        return self.protocol2_write_address( 0x07, [id] )


    def protocol2_write_address( self, addr, values_bytes ):
        addr_bytes = [ addr & 0xff, (addr >> 8 ) & 0xff ]
        msg = self.protocol2_assemble_msg(
            0x03,  # write instruction
            self.servo_id,
            addr_bytes + values_bytes
        )
        return self.send_instruction( msg )


    def protocol2_read_address(self, addr, nBytes=1):
        ''' reads nBytes from address on the servo.
            returns [n1,n2 ...] (list of parameters)
        '''
        addr_bytes = [ addr & 0xff, (addr >> 8 ) & 0xff ]
        len_bytes = [ nBytes & 0xff, (nBytes >> 8 ) & 0xff ]
        msg = self.protocol2_assemble_msg(
            0x02,  # read instruction
            self.servo_id,
            addr_bytes + len_bytes
        )
        return self.send_instruction( msg )


    def protocol2_assemble_msg(self, instruction, servo_id, parameter = []):
        packet_len = 1 + len( parameter ) + 2  # instruction + param + crc
        len_h = (packet_len >> 8) & 0xff
        len_l = packet_len & 0xff
        msg = [ 0xff, 0xff, 0xfd, 0x00 ]
        msg += [servo_id, len_l, len_h, instruction] + parameter
        c = crc( ''.join([ '%c'%(i) for i in msg ]))
        msg += [ c & 0xff, (c>>8) & 0xff ]
        return msg


    def protocol2_receive_reply(self):
        start = self.dyn.read_serial( 4 )
        if start != '\xff\xff\xfd\x00':
            raise RuntimeError('lib_robotis: Failed to receive start bytes\n')
        servo_id = self.dyn.read_serial( 1 )
        if ord(servo_id) != self.servo_id:
            raise RuntimeError('lib_robotis: Incorrect servo ID received: %d\n' % ord(servo_id))
        packet_len_l = ord( self.dyn.read_serial( 1 ) )
        packet_len_h = ord( self.dyn.read_serial( 1 ) )
        packet_len = (packet_len_h << 8) + packet_len_l
        if self.dyn.read_serial( 1 ) != '\x55':
            raise RuntimeError('lib_robotis: Unexpected response')
        err = self.dyn.read_serial( 1 )
        params = self.dyn.read_serial( packet_len - 4 ) # Ignore CRC, err, and \x55
        crc = self.dyn.read_serial( 2 ) # I'm not going to check...
        return [ord(v) for v in params], ord(err)


    def send_instruction( self, msg ):
        ''' Thread-safe version '''
        self.dyn.acq_mutex()
        try:
            self.send_serial( msg )
            data, err = self.protocol2_receive_reply()
        except:
            self.dyn.rel_mutex()
            raise
        self.dyn.rel_mutex()

        if err != 0:
            raise RuntimeError('lib_robotis: An error occurred: %d\n' % err)

        return data


    def send_serial(self, msg):
        """ sends the command to the servo (caller responsible for mutexes)
        """
        out = ''
        for m in msg:
            out += chr(m)
        self.dyn.send_serial( out )





def find_servos(dyn):
    ''' Finds all servo IDs on the USB2Dynamixel '''
    print 'Scanning for Servos.'
    servos = []
    dyn.servo_dev.setTimeout( 0.03 ) # To make the scan faster
    for i in xrange(254):
        try:
            s = Robotis_Servo2( dyn, i, series='XM' )
            print '\n FOUND A SERVO @ ID %d\n' % i
            servos.append( i )
        except:
            pass
    dyn.servo_dev.setTimeout( 1.0 ) # Restore to original
    return servos

def move_in(p):
    pass



if __name__ == '__main__':

    import time

    dyn = USB2Dynamixel_Device( 'COM7' )
    p = Robotis_Servo2( dyn, 1, series = "XM" )
    p.disable_torque()
    p.protocol2_write_address( 11, [3] )
    #print p.protocol2_read_address( 11 )
    p.enable_torque()
    p.move_angle(math.radians(-90),blocking=True) # Out
    time.sleep(1)
    p.disable_torque()
    sys.exit()

    #p.move_to_encoder( 0x7ff )
    time.sleep(5)
    p.move_angle(math.radians(-45)) # In
    #p.move_to_encoder( 0x000 )


    
    dyn = USB2Dynamixel_Device( 'COM7' )
    p = Robotis_Servo2( dyn, 1, series = "XM" )
    p.protocol2_write_address( 11, [3] )
    print p.move_to_encoder(300)

    print p.protocol2_read_address( 11 )
    print p.move_to_encoder(300)
    import sys
    sys.exit()

#    p.torque_mode()
#    p.move_angle(math.radians(135))

    p.protocol2_read_address( 11 ) 
    ipdb.set_trace()
    p.dyn.servo_dev.read(100)

    p.enable_torque()
#    p.set_torque(0)
    p.move_to_encoder(300)

    p.dyn.servo_dev.read(100)

#    p.move_angle(math.radians(90))
    ipdb.set_trace()

    p.protocol2_read_address( 11 ) 

#    p.torque_mode()
#    p.set_torque( 100 )  # 2.69mA/unit * 100 => 269mA current => 0.3 Nm according to torque curve


    p.move_angle(math.radians(90))


    try:
        while True:
            print p.read_torque()
    except KeyboardInterrupt:
        p.dyn.servo_dev.read(100)
        p.disable_torque()
        sys.exit(0)


from __future__ import division
from functions import calculate_line, RunningPrograms
from messages import *
from files import load_program, save_program
from constants import CONFIG
import time
import sys


def _notify_send(q_send, notify):
    """Wrapper to the notify class to send non empty values."""
    output = notify.output()
    if output:
        q_send.put(output)


def background_process(q_recv, q_send):
    try:
        notify.queue(START_THREAD)
        _notify_send(q_send, notify)
        
        store = {'Data': load_program(),
                 'Programs': {'Class': RunningPrograms(),
                              'Current': None,
                              'Previous': None},
                 'Resolution': None}
        
        notify.queue(DATA_LOADED)
        _notify_send(q_send, notify)
        
        while True:
            received_data = q_recv.get()
            try:
                messages = _background_process(q_send, received_data, store)
            except Exception as e:
                q_send.put('{}: line {}'.format(sys.exc_info()[2].tb_lineno, e))
                return
            
    except Exception as e:
        q_send.put('{}: {}'.format(sys.exc_info()[0], e))


def _background_process(q_send, received_data, store):

    check_resolution = False
    if 'Save' in received_data:
        notify.queue(SAVE_START)
        _notify_send(q_send, notify)
        if save_program(store['Programs']['Current'], store['Data']):
            notify.queue(SAVE_SUCCESS)
        else:
            notify.queue(SAVE_FAIL)
        _notify_send(q_send, notify)
    
    if 'Programs' in received_data:
        if received_data['Programs']:
            store['Programs']['Class'].reload_file()
            notify.queue(PROGRAM_RELOAD)
        else:
            store['Programs']['Class'].refresh()
            store['Programs']['Current'] = store['Programs']['Class'].check()
            if store['Programs']['Current'] != store['Programs']['Previous']:

                if store['Programs']['Current'] is None:
                    notify.queue(PROGRAM_QUIT)
                else:
                    notify.queue(PROGRAM_STARTED, store['Programs']['Current'])
                    
                notify.queue(SAVE_START)
                _notify_send(q_send, notify)
                
                check_resolution = True
                if save_program(store['Programs']['Previous'], store['Data']):
                    notify.queue(SAVE_SUCCESS)
                else:
                    notify.queue(SAVE_FAIL)
                _notify_send(q_send, notify)
    
                store['Programs']['Previous'] = store['Programs']['Current']
                    
                store['Data'] = load_program(store['Programs']['Current'])
                if store['Data']['Count']:
                    notify.queue(DATA_LOADED)
                else:
                    notify.queue(DATA_NOTFOUND)
        _notify_send(q_send, notify)


    if 'Resolution' in received_data:
        check_resolution = True
        store['Resolution'] = received_data['Resolution']

    if check_resolution:
        if store['Resolution'] not in store['Data']['Tracks']:
            store['Data']['Tracks'][store['Resolution']] = {}
        if store['Resolution'] not in store['Data']['Clicks']:
            store['Data']['Clicks'][store['Resolution']] = {}
        if store['Resolution'] not in store['Data']['Acceleration']:
            store['Data']['Acceleration'][store['Resolution']] = {}
    
    if 'Keys' in received_data:
        for key in received_data['Keys']:
            try:
                store['Data']['Keys'][key] += 1
            except KeyError:
                store['Data']['Keys'][key] = 1

    if 'MouseClick' in received_data:
        for mouse_click in received_data['MouseClick']:
            try:
                store['Data']['Clicks'][store['Resolution']][mouse_click] += 1
            except KeyError:
                store['Data']['Clicks'][store['Resolution']][mouse_click] = 1

    if 'MouseMove' in received_data:
        start, end = received_data['MouseMove']
        if start is None:
            mouse_coordinates = [end]
        else:
            mouse_coordinates = [start, end] + calculate_line(start, end)
        num_coordinates = len(mouse_coordinates)
        for pixel in mouse_coordinates:
            store['Data']['Tracks'][store['Resolution']][pixel] = store['Data']['Count']

            #Experimental fix for mouse snapping to top corner
            #Limit movement to a certain amount
            #Or make sure the mouse has only moved in a straight line
            topr_start = start == (0, 0)
            topr_end = end == (0, 0)
            if (not topr_start and not topr_end or num_coordinates < 30
                or topr_start and not topr_end and any(not c for c in end)
                or topr_end and not topr_start and any(not c for c in start)):
                try:
                    if store['Data']['Acceleration'][store['Resolution']][pixel] < num_coordinates:
                        raise KeyError()
                except KeyError:
                    store['Data']['Acceleration'][store['Resolution']][pixel] = num_coordinates
        store['Data']['Count'] += 1
        
        #Compress tracks if the count gets too high
        compress_frequency = CONFIG.data['CompressTracks']['Frequency']
        compress_multplier = CONFIG.data['CompressTracks']['Multiplier']
        compress_limit = compress_frequency * CONFIG.data['Main']['UpdatesPerSecond']
        if store['Data']['Count'] > compress_limit:
            notify.queue(MOUSE_TRACK_COMPRESS_START)
            _notify_send(q_send, notify)
            #Compress tracks
            tracks = store['Data']['Tracks']
            for resolution in tracks.keys():
                tracks[resolution] = {k: int(v // compress_multplier)
                                      for k, v in tracks[resolution].iteritems()}
                tracks[resolution] = {k: v for k, v in tracks[resolution].iteritems() if v}
                if not tracks[resolution]:
                    del tracks[resolution]
            #Compress acceleration
            accel = store['Data']['Acceleration']
            for resolution in accel.keys():
                accel[resolution] = {k: int(v // compress_multplier)
                                     for k, v in accel[resolution].iteritems()}
                accel[resolution] = {k: v for k, v in accel[resolution].iteritems() if v}
                if not accel[resolution]:
                    del accel[resolution]
            store['Data']['Count'] //= compress_multplier
            notify.queue(MOUSE_TRACK_COMPRESS_END)

    
    if 'Ticks' in received_data:
        store['Data']['Ticks'] += received_data['Ticks']

    _notify_send(q_send, notify)

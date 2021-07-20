#!/usr/bin/env python
# coding: utf-8

# In[1]:


import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyOAuth
from spotipy.oauth2 import SpotifyClientCredentials

import threading
import time

from gpiozero import LEDBoard
from gpiozero import RGBLED
from colorzero import Color


# Load credentials from file on PC. If you are downloading this project from Github, then this specific file will not be there because it contains private access information.

# In[2]:


scope = ['user-library-read', 'user-read-currently-playing', 'user-read-playback-state']
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))


# In[4]:


# Global variables of progress_ms and play_status. These are updated by thread 2 which does all
# of the refreshing with the Spotify server but are accessed by thread 1 which uses these to determine
# its stopping/starting behavior.

# Ideas for later:
# * Mood changes for second RGB light
# * Have error handling if a song analysis does not exist when grabbing from Spotify
# * Make it so changing position in song makes correct change
# * Fix bug if you spam changing song

lag_offset = 0.20

# GLOBAL VARS
progress_ms = 0
song_time = 0
play_status = True
time_since_refresh = 0
refresh_rate = 2 # Expressed in seconds
start_system_time = time.time()
viz_aa = {}
viz_bars = []
viz_beats = []
viz_bar_played = []
viz_beat_played = []
bar_pos = 0
beat_pos = 0
upcoming_bar_pos = 0
upcoming_beat_pos = 0

song_name = ''
song_uri = ''

blink_now = False

# Variable that keeps track of all threads should be running
should_play = True

leds = RGBLED(2, 4, 5)
leds_2 = RGBLED(17, 27, 22)

def pulse_led_col(led_ref, start_col, end_col, total_time):
    dir1_0 = end_col[0] - start_col[0]
    dir1_1 = end_col[1] - start_col[1]
    dir1_2 = end_col[2] - start_col[2]

    interval_change = 0.01 # How long to flip between colors (finer is smoother)
    num_changes = int((total_time / 2) / interval_change)
    
    # Up
    for i in range(0, num_changes):
        led_ref.value = (start_col[0] + (i / num_changes) * dir1_0, start_col[1] + (i / num_changes) * dir1_1, start_col[2] + (i / num_changes) * dir1_2)
        time.sleep(interval_change)
    for i in range(0, num_changes):
        led_ref.value = (end_col[0] - (i / num_changes) * dir1_0, end_col[1] - (i / num_changes) * dir1_1, end_col[2] - (i / num_changes) * dir1_2)
        time.sleep(interval_change)


# Change position in a song, start a new song, etc.
def refresh_song(playback, is_new_song):
    global bar_pos
    global beat_pos
    global song_name
    global song_uri
    global start_system_time
    global start_system_time
    global upcoming_bar_pos
    global upcoming_beat_pos
    global viz_aa
    global viz_bars
    global viz_beats
    global viz_bar_played
    global viz_beat_played
    global progress_ms
    
    progress_ms = playback['progress_ms']
    start_system_time = time.time()
    
    if is_new_song:
        song_name = playback['item']['name']
        song_uri = playback['item']['uri']
        viz_aa = sp.audio_analysis(song_uri)
        viz_bars = viz_aa['bars']
        viz_beats = viz_aa['beats']
    
    viz_bar_played = [False] * len(viz_bars)
    viz_beat_played = [False] * len(viz_beats)

    # Refresh the song playback progress because it can get out of sync after audio analysis
    quick_refresh = sp.current_playback()
    progress_ms = quick_refresh['progress_ms']
    progress_s = progress_ms / 1000

    # Optional lag offset
    progress_s += lag_offset

    for bi, bar_search in enumerate(viz_bars):
        if bar_search['start'] <= progress_s and progress_s < viz_bars[bi+1]['start']:
            bar_pos = bi
            upcoming_bar_pos = bi + 1
            # print('Found bar_pos', bar_pos)
            break
    for bi, beat_search in enumerate(viz_beats):
        if beat_search['start'] <= progress_s and progress_s < viz_beats[bi+1]['start']:
            beat_pos = bi
            upcoming_beat_pos = bi + 1
            # print('Found beat_pos', beat_pos)
            break


def visual_task(thread_lock):
    
    global should_play
    global song_name
    global song_uri
    global start_system_time
    global viz_aa
    global viz_bars
    global viz_beats
    global viz_bar_played
    global viz_beat_played
    global bar_pos
    global beat_pos
    global upcoming_bar_pos
    global upcoming_beat_pos
    global progress_ms

    global blink_now
    
    # Start the visualization task (Don't worry about refreshes or anything)
    thread_lock.acquire()
    viz_song = sp.current_playback()
    refresh_song(viz_song, True)
    thread_lock.release()

    timeout = time.time() + 40 # How long to have the below run for

    print('Now playing \'', song_name, '\'', sep='')

    while should_play: 
        # Find our current time in the song
        thread_lock.acquire()
        play_time = time.time() - start_system_time
        song_time = (progress_ms / 1000) + play_time # Actual place in spotify track
        # print('progress_s', progress_ms / 1000)
        thread_lock.release()

        # Optional lag adjustment
        song_time += lag_offset

        # Exit if timeout
        # if time.time() > timeout:
            # print('Timeout.')
            # should_play = False

        thread_lock.acquire()
        # Trigger event if current song position is greater than upcoming bar beat
        if viz_bars[upcoming_bar_pos]['start'] <= song_time and not viz_bar_played[bar_pos]:
            #print('BAR')
            viz_bar_played[bar_pos] = True
            bar_pos += 1
            upcoming_bar_pos += 1

        # print('beat time:', viz_beats[upcoming_beat_pos]['start'])
        # print('played:', viz_beat_played[beat_pos])
        # print('song time:', song_time)
        
        # print(viz_beats)
        if viz_beats[upcoming_beat_pos]['start'] <= song_time and not viz_beat_played[beat_pos]:
            #print('BEAT', upcoming_beat_pos)
            blink_now = True

            viz_beat_played[beat_pos] = True
            beat_pos += 1
            upcoming_beat_pos += 1
        thread_lock.release()

        # Have a small delay to not clog CPU
        time.sleep(0.001)

def server_refresh(thread_lock):
    global bar_pos
    global beat_pos
    global song_name
    global song_uri
    global start_system_time
    global start_system_time
    global upcoming_bar_pos
    global upcoming_beat_pos
    global viz_aa
    global viz_bars
    global viz_beats
    global viz_bar_played
    global viz_beat_played
    global progress_ms
    global should_play
    global time_since_refresh
    
    last_time_thread2 = time.time()
    
    while should_play:
        time_since_refresh += time.time() - last_time_thread2
        last_time_thread2 = time.time()

        # Refresh progress every once in a while
        if time_since_refresh > refresh_rate:
            time_since_refresh -= refresh_rate
            refresh = sp.current_playback()
            
            if not (refresh['item'] is None):
                # Check if new song has appeared
                if refresh['item']['uri'] != song_uri:
                    thread_lock.acquire()
                    refresh_song(refresh, True)
                    print('Now playing \'', song_name, '\'', sep='')
                    thread_lock.release()

                # Check if we should stop song if playback stops
                if not refresh['is_playing']:
                    thread_lock.acquire()
                    print('Exit: song not playing')
                    should_play = False
                    thread_lock.release()

        time.sleep(0.50) # Don't clog CPU

color_1_vals = [1.0, 0.0, 0.0]
color_2_vals = [0, 0, 0]
is_dimming = False
color_pos = 1

def led_manage(thread_lock):
    global should_play
    global blink_now
    global leds, color_1_vals, is_dimming, color_pos
    
    while should_play:
        # Blink effect to beat
        if blink_now:
            # leds.value = (1, 0.5, 0.5) 
            # temp = color_1_vals.copy()
            # if is_dimming:
            #     temp[(color_pos+2)%3] += 0.5
            #     leds.value = tuple(temp)
            # else:
            #     temp[(color_pos+1)%3] += 0.5
            #     leds.value = tuple(temp)
            # temp = color_1_vals.copy()
            # if is_dimming:
            #     temp[(color_pos+1)%3] = 0.5
            # else:
            #     temp[(color_pos+2)%3] = 0.5

            # print('col:', color_1_vals)
            # print('temp:', temp)

            # leds.value = tuple(temp)
            # leds_2.value = (0.30, 0.20, 0.92)
            # leds_2.value = (0.09, 0, 0.76)
            # time.sleep(0.05)
            # leds.value = (0, 0, 0)
            # leds_2.value = (0.20, 0.73, 0.92)
            # leds_2.value = (0.30, 0.20, 0.92)
            # pulse_led_col(leds_2, (0.09, 0, 0.76), (0.20, 0.73, 0.92), 0.15) # Medium subtle
            # pulse_led_col(leds_2, (0.20, 0.73, 0.92), (0.40, 0.55, 0.92), 0.20) # Really subtle
            pulse_led_col(leds_2, (0.20, 0.73, 0.92), (0.86, 0.26, 0.96), 0.20) # Not subtle
            thread_lock.acquire()
            blink_now = False
            thread_lock.release()
        time.sleep(0.01)

        # Strobe effect 
        if is_dimming:
            if color_1_vals[color_pos] > 0:
                color_1_vals[color_pos] -= 0.02
                if color_1_vals[color_pos] <= 0:
                    color_1_vals[color_pos] = 0
            else:
                color_1_vals[color_pos] = 0
                is_dimming = False
                color_pos += 2
                color_pos %= 3
        else:
            if color_1_vals[color_pos] < 1.0:
                color_1_vals[color_pos] += 0.02
                if color_1_vals[color_pos] >= 1:
                    color_1_vals[color_pos] = 1
            else:
                is_dimming = True
                color_pos -= 1
                color_pos %= 3

        # Update
        leds.value = tuple(color_1_vals)

        
# In[5]:


lock = threading.Lock()

viz_thread = threading.Thread(target=visual_task, args=(lock,))
refresh_thread = threading.Thread(target=server_refresh, args=(lock,))
blink_thread = threading.Thread(target=led_manage, args=(lock,))

refresh_thread.start()
viz_thread.start()
blink_thread.start()

viz_thread.join()
refresh_thread.join()
blink_thread.join()


# In[51]:


# Percentage completion of song
progress_ms / (viz_aa['track']['duration'] * 1000)


#!/usr/bin/env python
# coding: utf-8

# In[1]:


run_pi = False
output_console = True

import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyOAuth
from spotipy.oauth2 import SpotifyClientCredentials

import threading
import time

if run_pi:
    from gpiozero import LEDBoard
    from gpiozero import RGBLED
    from colorzero import Color


# Load credentials from file on PC. If you are downloading this project from Github, then this specific file will not be there because it contains private access information.

# In[2]:


scope = ['user-library-read', 'user-read-currently-playing', 'user-read-playback-state']
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))


# In[3]:


# test_analysis = sp.audio_analysis('https://open.spotify.com/track/6vSq5q5DCs1IvwKIq53hj2?si=94fe9e98a84a4ca8')


# In[4]:


# Global variables of progress_ms and play_status. These are updated by thread 2 which does all
# of the refreshing with the Spotify server but are accessed by thread 1 which uses these to determine
# its stopping/starting behavior.

# Ideas for later:
# * Mood changes for second RGB light
# * Have error handling if a song analysis does not exist when grabbing from Spotify
# * Make it so changing position in song makes correct change
# * Fix bug if you spam changing song

lag_offset = 0
lag_offset_nudge = 0.20

# GLOBAL VARS
progress_ms = 0
song_time = 0
play_status = True
time_since_refresh = 0
refresh_rate = 3 # Expressed in seconds
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

# Initialize pins
if run_pi:
    leds = RGBLED(2, 4, 5)
    leds_2 = RGBLED(17, 27, 22)
    color_1_vals = [1.0, 0.0, 0.0]
    color_2_vals = [0, 0, 0]
    is_dimming = False
    color_pos = 1

    
# Pulses an LED between two colors, we pulse this way to make it
# not super jarring to the viewer if we suddenly flip colors.
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
        if output_console:
            print('Now playing \'', song_name, '\'', sep='')
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
    progress_s += lag_offset + lag_offset_nudge

    for bi, bar_search in enumerate(viz_bars):
        if bi == 0:
            if progress_s <= bar_search['start']:
                bar_pos = 0
                upcoming_bar_pos = 1
                break
        else:
            if viz_bars[bi-1]['start'] <= progress_s and progress_s < bar_search['start']:
                bar_pos = bi
                upcoming_bar_pos = bi + 1
                break

    for bi, beat_search in enumerate(viz_beats):
        if bi == 0:
            if progress_s <= beat_search['start']:
                beat_pos = 0
                upcoming_beat_pos = 1
        else:
            if viz_beats[bi-1]['start'] <= progress_s and progress_s < beat_search['start']:
                beat_pos = bi
                upcoming_beat_pos = bi + 1
                break


# Manage the timing of the song and making sure we trigger the right events when the beats are hit
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
    global song_time
    global blink_now
    
    # Start the visualization task up: we start by refreshing
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
        song_time += lag_offset + lag_offset_nudge

        # Exit if timeout
        # if time.time() > timeout:
            # print('Timeout.')
            # should_play = False

        thread_lock.acquire()
        # Trigger event if current song position is greater than upcoming bar beat
        if viz_bars[bar_pos]['start'] <= song_time and not viz_bar_played[bar_pos]:
            #print('BAR')
            viz_bar_played[bar_pos] = True
            bar_pos += 1
            upcoming_bar_pos += 1

        # print('beat time:', viz_beats[upcoming_beat_pos]['start'])
        # print('played:', viz_beat_played[beat_pos])
        # print('song time:', song_time)
        
        # print(viz_beats)
        if viz_beats[beat_pos]['start'] <= song_time and not viz_beat_played[beat_pos]: 
            if run_pi:
                blink_now = True
            else:
                print('BEAT', upcoming_beat_pos, 'T:', viz_beats[beat_pos]['start'], 'ST:', song_time, 'Diff:', song_time - viz_beats[beat_pos]['start'])

            viz_beat_played[beat_pos] = True
            beat_pos += 1
            upcoming_beat_pos += 1
            
        thread_lock.release()

        # Have a small delay to not clog CPU
        time.sleep(0.005)


# Function to refresh with the Spotify server and check if a song has changed,
# we are in a new place in the song, the song has paused, etc.
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
            before_refresh_song_time = song_time
            refresh = sp.current_playback()
            
            if not (refresh['item'] is None):
                # Check if new song has appeared
                if refresh['item']['uri'] != song_uri:
                    thread_lock.acquire()
                    refresh_song(refresh, True)
                    thread_lock.release()
                    
                # Try adjusting lag amount?
                refresh_diff = (refresh['progress_ms'] / 1000) - before_refresh_song_time
                other_diff = (refresh['progress_ms'] / 1000) - song_time
                #print('rf:', refresh_diff)
                #print('o:', other_diff)
                #lag_offset = other_diff
                    
                # print('refresh diff:', (refresh['progress_ms'] / 1000) - before_refresh_song_time)
                if refresh['item']['uri'] == song_uri and abs(refresh_diff) > 0.50:
                    # Check if in new part of the song
                    thread_lock.acquire()
                    print('Same song different time')
                    refresh_song(refresh, False)
                    thread_lock.release()

                # Check if we should stop song if playback stops
                if not refresh['is_playing']:
                    thread_lock.acquire()
                    print('Exit: song not playing')
                    should_play = False
                    thread_lock.release()

        time.sleep(0.50) # Don't clog CPU


# Handle the Raspberry Pi GPIO for the LEDs
def led_manage(thread_lock):
    global should_play
    global blink_now
    global leds, color_1_vals, is_dimming, color_pos
    
    while should_play:
        # Blink effect to beat
        if blink_now:
            # pulse_led_col(leds_2, (0.09, 0, 0.76), (0.20, 0.73, 0.92), 0.15) # Medium subtle
            # pulse_led_col(leds_2, (0.20, 0.73, 0.92), (0.40, 0.55, 0.92), 0.20) # Really subtle
            pulse_led_col(leds_2, (0.20, 0.73, 0.92), (0.86, 0.26, 0.96), 0.20) # Not subtle

            thread_lock.acquire()
            blink_now = False
            thread_lock.release()
            
        time.sleep(0.01)

        # Strobe effect on LED 1
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
if run_pi:
    blink_thread = threading.Thread(target=led_manage, args=(lock,))

refresh_thread.start()
viz_thread.start()
if run_pi:
    blink_thread.start()

viz_thread.join()
refresh_thread.join()
if run_pi:
    blink_thread.join()


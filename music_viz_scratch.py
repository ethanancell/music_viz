#!/usr/bin/env python
# coding: utf-8

# In[20]:


import spotipy
import spotipy.util as util
from spotipy.oauth2 import SpotifyOAuth
from spotipy.oauth2 import SpotifyClientCredentials

import threading
import time


# Load credentials from file on PC. If you are downloading this project from Github, then this specific file will not be there because it contains private access information.

# In[21]:


scope = ['user-library-read', 'user-read-currently-playing', 'user-read-playback-state']
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))


# In[24]:


# Global variables of progress_ms and play_status. These are updated by thread 2 which does all
# of the refreshing with the Spotify server but are accessed by thread 1 which uses these to determine
# its stopping/starting behavior.
progress_ms = 0
song_time = 0
play_status = True
time_since_refresh = 0
refresh_rate = 5 # Expressed in seconds
start_system_time = time.time()

# Variable that keeps track of all threads should be running
should_play = True

def visual_task(thread_lock):
    
    global should_play
    
    # Start the visualization task (Don't worry about refreshes or anything)
    viz_song = sp.current_playback()
    song_name = viz_song['item']['name']
    song_uri = viz_song['item']['uri']
    
    thread_lock.acquire()
    progress_ms = viz_song['progress_ms']
    start_system_time = time.time()
    thread_lock.release()

    timeout = time.time() + 40 # How long to have the below run for

    viz_aa = sp.audio_analysis(song_uri)
    viz_bars = viz_aa['bars']
    viz_beats = viz_aa['beats']

    # Keep track of what has been played or not
    viz_bar_played = [False] * len(viz_bars)
    viz_beat_played = [False] * len(viz_beats)

    need_find_pos = True
    bar_pos = 0
    beat_pos = 0
    upcoming_bar_pos = 1
    upcoming_beat_pos = 1

    print('Now playing \'', song_name, '\'', sep='')

    while should_play: 
        # Find our current time in the song
        play_time = time.time() - start_system_time
        
        thread_lock.acquire()
        song_time = (progress_ms / 1000) + play_time # Actual place in spotify track
        thread_lock.release()

        # Exit if timeout
        if time.time() > timeout:
            should_play = False

        # If first loop, find the current position of the beat
        if need_find_pos:
            # Refresh the song playback progress because it can get out of sync. This is
            # the only place where this refresh is done inside this thread 1
            refresh = sp.current_playback()
            progress_ms = refresh['progress_ms']
            song_time = progress_ms / 1000 + play_time

            for bi, bar_search in enumerate(viz_bars):
                if bar_search['start'] <= song_time and song_time < viz_bars[bi+1]['start']:
                    bar_pos = bi
                    upcoming_bar_pos = bi + 1
                    # print('Found bar_pos', bar_pos)
                    break
            for bi, beat_search in enumerate(viz_beats):
                if beat_search['start'] <= song_time and song_time < viz_beats[bi+1]['start']:
                    beat_pos = bi
                    upcoming_beat_pos = bi + 1
                    # print('Found beat_pos', beat_pos)
                    break
            need_find_pos = False

        # Trigger event if current song position is greater than upcoming bar beat
        if viz_bars[upcoming_bar_pos]['start'] <= song_time and not viz_bar_played[bar_pos]:
            #print('BAR')
            viz_bar_played[bar_pos] = True
            bar_pos += 1
            upcoming_bar_pos += 1

        if viz_beats[upcoming_beat_pos]['start'] <= song_time and not viz_beat_played[beat_pos]:
            print('BEAT\r')
            viz_beat_played[beat_pos] = True
            beat_pos += 1
            upcoming_beat_pos += 1

        # Have a small delay to not clog CPU
        time.sleep(0.05)

def server_refresh(thread_lock):
    global time_since_refresh
    global progress_ms
    global should_play
    
    last_time_thread2 = time.time()
    
    while should_play:
        time_since_refresh += time.time() - last_time_thread2
        last_time_thread2 = time.time()

        # Refresh progress every once in a while
        if time_since_refresh > refresh_rate:
            time_since_refresh -= refresh_rate
            refresh = sp.current_playback()

            thread_lock.acquire()
            progress_ms = refresh['progress_ms']
            thread_lock.release()
            
            # Check if we should stop song if playback stops
            if not refresh['is_playing']:
                thread_lock.acquire()
                should_play = False
                thread_lock.release()

        time.sleep(0.50) # Don't clog CPU


# In[25]:


lock = threading.Lock()

viz_thread = threading.Thread(target=visual_task, args=(lock,))
refresh_thread = threading.Thread(target=server_refresh, args=(lock,))

refresh_thread.start()
viz_thread.start()
viz_thread.join()
refresh_thread.join()


# In[51]:


# Percentage completion of song
progress_ms / (viz_aa['track']['duration'] * 1000)


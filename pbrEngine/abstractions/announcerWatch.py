import logging
import gevent
import os
import json
from datetime import datetime
from collections import namedtuple


logger = logging.getLogger("pbrEngine")

NO_TRACK = 0xFFFFFFFF
Track = namedtuple("Track", "infoindex duration transcription path")

class AnnouncerWatch:
    """Detect when PBR begins playing announcer lines by watching memory.

    Announcer lines are stored as individual tracks in the PBR ISO's pbr_sounds.brsar archive.
    The infoindex of a track corresponds to the track's unique index in the INFO table of this archive.

    For AnnouncerWatch to perform detection, the PBREngine object calls the onNewTrackValue
    and onNewTrackPlayingFlag functions whenever their respective memory locations change in value.

    pbr_sounds.brsar can be extracted and manipulated with a modified version of BrawlBox.
    See https://github.com/suludas/brawltools/commit/5ae6ec17f36a2833fb2a977999d15ce69edcc03b

    Only the PAL ISO loaded in English is supported.
    """
    def __init__(self, trackPlayingEventHook):
        """
        :param trackPlayingEventHook: AnnouncerWatch calls this EventHook when it detects that
            PBR has begun to play an announcer track.
            Called with these arguments:
                arg0: <infoindex> The track's infoindex.
                arg1: <duration> Duration of the announcer line in seconds.
                arg2: <transcription> English transcription of the announcer line.
                arg3: <path> Relative path of the WAV sound, as per brawlbox extraction.
        """
        self.enabled = True
        self.trackPlayingEventHook = trackPlayingEventHook
        self._channelVal = [NO_TRACK, NO_TRACK]          # Most recently seen value on each channel.
        self._prevChannelVal = [NO_TRACK, NO_TRACK]      # Value prior to the most recently seen value on each channel.
        self._isChannelPlaying = [False, False]          # Most recently seen value on each channel flag.
        self._trackPlayDetections = [NO_TRACK, NO_TRACK] # Which tracks we've detected as playing on each channel.
                                                         #   We return this value to NO_TRACK when a track is unloaded.
        self._tracks = {}                                # All PBR tracks (as Track objects) by their infoindex.

        self_path = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(self_path, '../data/announcer_tracks.json'), 'r', encoding='utf-8') as file:
            for track in json.load(file):
                self._tracks[track['infoindex']] = Track(**track)

    def onNewTrackValue(self, newVal, channel):
        """Actions to take when a new value appears in the ANNOUNCER_CHANNEL[0|1] memory locations.

        :param newVal:
            If not 0 or NO_TRACK(0xFFFFFFFF), this value is the infoIndex of an announcer track that is going to play
            now or soon on this channel. All announcer tracks are contained in the iso's pbr_sounds.brsar archive. The
            infoIndex corresponds to the track's unique index in the INFO table of this archive.
        :param channel:
            Which channel location this value appeared in. Can be 0 or 1.

        A separate flag monitored by self.onNewChannelPlayingFlag() determines when the track will start playing.
        It usually plays immediately, or after a brief delay to allow the other channel to finish* playing a track.

        When a channel is finished playing a track, its value becomes NO_TRACK if no other tracks need to play.

        Occasionally a channel's value changes to 0 and then immediately back to its previous value. This is likely the
        same "invalid read value" issue that plagues reads/watches in the 0x9xxxxxxx region, and is described in
        abstractions/dolphinIO:readMulti.

        * In extremely rare instances, PBR has been heard playing two overlapping announcer lines.

        Below are somewhat irrelevant additional notes on channel behavior:

        It's fairly common for two channels to change value at the same time, with one having said delay before playing.
        When PBR needs to play a new track, it follows these rules:
            1. If the channel that previously played track is IDLE, that channel gets the new track.
            2. Otherwise, either channel may load the track. Usually the alternate channel is used.
        """
        if not self.enabled:
            return
        curVal = self._channelVal[channel]
        prevVal = self._prevChannelVal[channel]

        # Update recorded values.
        self._prevChannelVal[channel] = self._channelVal[channel]
        self._channelVal[channel] = newVal

        if newVal == 0:
            # Ignore- invalid read value.
            logChannelValue(newVal, channel, "NEW_VAL_IGNORE")
        elif newVal == NO_TRACK:
            # Clear play detection for this track.  That way if it gets loaded and played again,
            # we won't mistakenly assume we've already detected this track to have played already.
            # PBR has brief (~.4s) silent tracks that it does occasionally load and play again in this fashion.
            self._trackPlayDetections[channel] = NO_TRACK
            if curVal == 0 and prevVal == NO_TRACK:
                # Ignore- returning to NO_TRACK after brief invalid read value.
                logChannelValue(newVal, channel, "NEW_VAL_IGNORE")
            else:
                logChannelValue(newVal, channel, "NO_TRACK")
        else:
            if curVal == 0 and prevVal == newVal:
                # Ignore- newVal is just returning back to prevVal after briefly reading as 0 (invalid read value).
                logChannelValue(newVal, channel, "NEW_TRACK_IGNORE")
            else:
                # A new track appeared on this channel.
                if newVal not in self._tracks:
                    logChannelValue(newVal, channel, "INVALID_NEW_INFOINDEX", logging.ERROR)
                elif self._isChannelPlaying[channel]:
                    # A channel's isPlaying flag might not flip off and back on in between back-to-back tracks.
                    # So if the channel's still playing, maybe this new track gets played immediately.
                    # But we don't know for sure- sometimes the new track appears just before (~<.03s) the
                    # channel's isPlaying flag switches off in memory. Greenlet racing might be to blame.
                    # If the flag's still up after a brief sleep, assume the new track gets played immediately.
                    #
                    # If after sleeping the flag is incorrectly off due to an brief invalid read, it is no concern-
                    # the track will just play when the flag switches back on.
                    #
                    # Perhaps this would cause a variety of bugs with extremely short tracks (~<.1s) but
                    # thankfully PBR doesn't have such tracks.
                    logChannelValue(newVal, channel, "NEW_TRACK_SLEEP", logging.DEBUG)
                    gevent.sleep(0.08)
                    if self._isChannelPlaying[channel]:
                        if newVal == self._trackPlayDetections[channel]:
                            # Ignore- already detected this track as playing.
                            # This will happen when:
                            #   The isPlaying flag flips off just after the new track appears on the channel
                            #   (even though it PBR wasn't actually playing the track yet)
                            #   and then PBR actually starts playing the track before this function wake up,
                            #   causing the onNewTrackPlayingFlag function to queue the track before this function woke.
                            logChannelValue(newVal, channel, "POST_SLEEP_PLAY_REDUNDANT")
                        else:
                            # Assume PBR is playing this track.
                            logChannelValue(newVal, channel, "POST_SLEEP_PLAY", logging.DEBUG)
                            self._new_track_play_detected(newVal)
                    else:
                        # PBR isn't playing this track yet.
                        logChannelValue(newVal, channel, "POST_SLEEP_NO_PLAY", logging.DEBUG)
                else:
                    # PBR isn't playing this track yet.
                    logChannelValue(newVal, channel, "NEW_TRACK", logging.DEBUG)

    def onNewTrackPlayingFlag(self, isPlaying, channel):
        """Actions to take when a new value appears in the ANNOUNCER_CHANNEL[0|1]_IS_PLAYING locations.

        :param isPlaying:
            bool for whether the channel is playing its track.
        :param channel:
            Which channel, 0 or 1.
        """
        # Update recorded values.
        if not self.enabled:
            return
        self._isChannelPlaying[channel] = isPlaying

        # If the channel value is 0 (the invalid read value) then try the previous channel value.
        infoindex = self._channelVal[channel] or self._prevChannelVal[channel]

        if isPlaying:
            if infoindex in (0, NO_TRACK) or infoindex not in self._tracks:
                # Unexpected error- where's the track that's playing?
                logChannelValue(infoindex, channel, "INVALID_INFOINDEX", logging.ERROR)
            else:
                if infoindex == self._trackPlayDetections[channel]:
                    # Ignore- already queued this track for playing.
                    # Occurs if the flag turns off briefly due to an invalid 0 read value.
                    logChannelValue(infoindex, channel, "FLAG_PLAY_REDUNDANT")
                else:
                    # Assume PBR is playing the track on this channel.
                    logChannelValue(infoindex, channel, "FLAG_PLAY", logging.DEBUG)
                    # Record that we've detected this track as having begun to play.
                    self._trackPlayDetections[channel] = infoindex
                    self._new_track_play_detected(infoindex)
        else:
            logChannelValue(infoindex, channel, "FLAG_STOP", logging.DEBUG)

    def _new_track_play_detected(self, infoindex):
        track = self._tracks[infoindex]
        logger.debug(f"Detected track {infoindex} playing: {track.transcription}")
        self.trackPlayingEventHook(**track._asdict())


def logChannelValue(value, channel, category, logLevel=logging.DEBUG):
    dtStr = ""
    # dtStr = f"[{datetime.now().time()}] "  # Uncomment to show datetime in the console for debugging.
    valueStr = f"0x{value:X}" if value == NO_TRACK else f"{value}"
    logger.log(logLevel, f"{dtStr}ch{channel} {category}: {valueStr}")

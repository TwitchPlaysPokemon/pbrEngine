import logging
import gevent
from gevent.event import AsyncResult

from ..memorymap.addresses import LocPath, isValidLoc

logger = logging.getLogger("pbrEngine")


class DolphinIO:
    def __init__(self, dolphin, crash_callback):
        self._dolphin = dolphin
        self._crash_callback = crash_callback

    def read8(self, addr, **kwargs):
        return self.read(8, addr, **kwargs)

    def read16(self, addr, **kwargs):
        return self.read(16, addr, **kwargs)

    def read32(self, addr, **kwargs):
        return self.read(32, addr, **kwargs)

    def read(self, mode, addr, **kwargs):
        return self.readMulti([(mode, addr)], **kwargs)[0]

    def readMulti(self, readTuplesList, numAttempts=5):
        ''' Return a list of memory values corresponding to a list of (mode, addr) tuples
    
        Memory is batch read <num_reads> times, with a 10ms wait between batches. Exists
        because the 0x9xxxxxxx addresses occasionally read as 0 instead of the correct
        value. This occurs approximately once every 1,000 reads. With a second read after
        10ms, this reduces to once every 250,000 reads.
        '''
        results = [0] * len(readTuplesList)
        if numAttempts <= 0:
            raise ValueError("numAttempts must be > 0")
        for i in range(numAttempts):
            temp_results = []
            for mode, addr in readTuplesList:
                if mode not in (8, 16, 32):
                    raise ValueError("Mode must be 8, 16, or 32, got {}".format(mode))
                ar = AsyncResult()
                temp_results.append(ar)
                self._dolphin.read(mode, addr, ar.set)
            for i, ar in enumerate(temp_results):
                val = ar.get()
                if val != 0:
                    results[i] = val
            if i < numAttempts - 1:
                gevent.sleep(0.01)  # Sleep a bit between read batches
        return results

    def write8(self, addr, val, **kwargs):
        self.write(8, addr, val, **kwargs)

    def write16(self, addr, val, **kwargs):
        self.write(16, addr, val, **kwargs)

    def write32(self, addr, val, **kwargs):
        self.write(32, addr, val, **kwargs)

    def write(self, mode, addr, val, **kwargs):
        self.writeMulti([(mode, addr, val)], **kwargs)

    def writeMulti(self, writeTuplesList, maxAttempts=3, writesPerAttempt=5,
                   readsPerAttempt=2, crashOnFail=True):
        '''Write multiple values to memory, given a list of (mode, addr, val) tuples
    
        On each attempt, memory is batch written <writesPerAttempt> times, with a 10ms
        wait between batches. Exists because the 0x9xxxxxxx addresses occasionally fail 
        to write the correct value.  This occurs approximately once every 1,000 writes.
    
        If <readsPerAttempt> is nonzero, each attempt is verified by reading back the 
        memory.  If a discrepancy exists, up to <maxAttempts> will be performed.  Note 
        that discrepancies can arise due to faulty reads as well as faulty writes.
        '''
        writes_needed = writeTuplesList
        assert maxAttempts > 0, "maxAttempts must be > 0"
        assert writesPerAttempt > 0, "writesPerAttempt must be > 0"
        assert readsPerAttempt >= 0, "readsPerAttempt must be >= 0"
        assert maxAttempts == 1 if readsPerAttempt == 0 else True, "maxAttempts must be 1 when not verifying reads (readsPerAttempt == 0)"
        for i in range(maxAttempts):
            # Write all values for which writing is needed
            for write_i in range(writesPerAttempt):
                for mode, addr, val in writes_needed:
                    if mode not in (8, 16, 32):
                        raise ValueError("Mode must be 8, 16, or 32, got {}".format(mode))
                    self._dolphin.write(mode, addr, val)
                if write_i < writesPerAttempt - 1:
                    gevent.sleep(0.01)  # Sleep a bit between write batches
            # Perform verification on values written
            if readsPerAttempt > 0:
                # Read all values that were written
                read_values = self.readMulti([(m, a) for m, a, v in writes_needed],
                                              numAttempts=readsPerAttempt)
                # Filter out writes for which the read value matched the written value
                writes_needed = [(m, a, v) for i, (m, a, v) in enumerate(writes_needed)
                                 if read_values[i] != v]
                if not writes_needed:
                    return  # All values to write were successfully verified
            if i < maxAttempts - 1:
                gevent.sleep(0.01)  # Sleep a bit between attempts
        if readsPerAttempt > 0 and writes_needed and crashOnFail:
            logger.error("The following memory writes failed: {}"
                         .format(writes_needed))
            self._crash_callback("Memory write failure")

    def readNestedAddr(self, nestedLocation, maxAttempts=5, readsPerAttempt=3,
                      crashOnFail=True):
        '''Get final address of a nested pointer
    
        Performs up to <max_attempts> of <reads_per_attempt> to reduce
        chance of faulty reads.
    
        Returns the address, or None if final address is not a valid memory location.
        '''
        nestedLoc = nestedLocation.value
        loc = nestedLoc.startingAddr
        path = LocPath()
        path.append(loc)
        for offset in nestedLoc.offsets:
            val = 0
            for i in range(maxAttempts):
                val = self.read32(loc, numAttempts=readsPerAttempt)
                if isValidLoc(val):
                    break
                else:
                    faultyPath = LocPath(path)
                    faultyPath.append(val + offset)
                    logger.error("Location detection for {} failed attempt {}/{}. Path: {}"
                                 .format(nestedLocation.name, i, maxAttempts, faultyPath))
                gevent.sleep(0.2)  # Sleep a bit, this helps a lot with bad reads
            loc = val + offset
            path.append(loc)
            if not isValidLoc(loc):
                logger.error("Invalid pointer location for {}. Path: {}"
                             .format(nestedLocation.name, path))
                if crashOnFail:
                    self._crash_callback(reason="Failed to read pointer")
                return None
        return loc

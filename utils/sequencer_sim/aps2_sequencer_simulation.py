import numpy as np
from queue import Queue

from QGL.drivers.APS2Pattern import *

class InvalidSequencerState(Exception):
    pass

class BadAddress(Exception):
    pass

class BadInstruction(Exception):
    pass

class VRAMentry(object):
    """
    A representation of an entry in the validity RAM.
    """
    __slots__ = ['data', 'validity']
    
    def __init__(self, data = 0x0, validity = 0x0):
        self.data = np.uint32(data)
        self.validity = np.uint32(validity)
        
    def invalidate(self, mask=0x0, flag=False):
        mask = np.uint32(mask) #ugly...
        if flag:
            self.validity = self.validity & ~mask
        else:
            self.validity = mask
            
    def store(self, value, flag=False):
        value = np.uint32(value)
        if flag:
            self.data = (self.data & ~self.validity) | value
        else:
            self.data = value
            
    def set_valid(self):
        self.validity = 0xFFFFFFFF
        
    def test_valid(self, mask):
        mask = np.uint32(mask)
        return (mask & self.validity) == mask

class OutputEngine(object):
    
    def __init__(self):
        self.fifo   = Queue() #pending commands
        self.output = [] #the output
    
    def write(self):
        while not self.fifo.empty():
            self.output.append(self.fifo.get())

class WaveformEngine(OutputEngine):
            
    def play_waveform(self, wave):
        self.fifo.put(wave)
        
    def play_TA(self, value, count):
        self.fifo.put(np.full(count, value, dtype=np.complex))
        
class MarkerEngine(OutputEngine):
    
    def play_marker(self, state, count, tword=0):
        #ignore transition word for now...
        data = np.full(count, state, dtype=np.uint8)
        self.fifo.put(data)
     
class APS2Sequencer:
    
    def __init__(self, seq_memory_size=1024, VRAMsize=16, 
                 max_step=2048, stop=None):
        
        self.ip  = 0 #the instruction pointer (IP)
        self.cmp = 0 #the comparison register (CMP)
        self.rep = 0 #the repeat counter (REP)
        self.stack = [] #IP, REP stack
        self.cmp_result = False
        
        #Sequence and waveform memory
        self.seq_mem  = [NoOp() for _ in range(seq_memory_size)]
        self.wave_mem = []
        
        #VRAM
        self.vram = [VRAMentry() for _ in range(VRAMsize)]
        
        #Output engines
        self.wengine = WaveformEngine()
        self.mengine = [MarkerEngine() for _ in range(4)]
        
        #Don't try to solve the halting problem!
        self.halt = False
        self.max_step = max_step
        self.stop = stop if stop else self.max_step
    
    def _seq_addr_ok(self, addr):
        if ((addr < 0) or (addr > len(self.seq_mem)-1)):
            raise BadAddress(f"Sequence address out of bounds!")
            
    def _wav_addr_ok(self, addr):
         if ((addr < 0) or (addr > len(self.wave_mem)-1)):
            raise BadAddress(f"Waveform address out of bounds!")  
            
    def _vram_addr_ok(self, addr):
        if ((addr < 0) or (addr > len(self.vram)-1)):
            raise BadAddress(f"VRAM address out of bounds!")
    
    def check_state_valid(self):
        if ((self.ip < 0) or (self.ip > len(self.seq_mem)-1)):
            raise InvalidSequencerState(f"Instruction pointer out of bounds: {self.ip}")
        if self.rep < 0:
            raise InvalidSequencerState(f"Negative repeat counter!")
    
    ## INSTRUCTIONS
    
    def noop(self):
        self.ip += 1
        
    def prefetch(self,addr):
        raise NotImplementedError("Prefetching not yet implemented!")
        self._seq_addr_ok()
        self.ip += 1
    
    def sync(self):
        self.ip +=1
    
    def wait(self):
        self.ip +=1 
    
    def waveform(self, addr, count, ta_bit=False):
        self._wav_addr_ok(addr)
        if ta_bit:
            self.wengine.play_TA(self.wave_mem[addr], count)
        else:
            self.wengine.play_waveform(self.wavemem[addr:addr+count])
        self.ip += 1
            
    def modulator(self):
        self.ip += 1
    
    def marker(self, channel, state, count):
        self.mengine[channel].play_marker(state,count)
        self.ip += 1
        
    def goto(self, addr):
        self._seq_addr_ok(addr)
        if self.cmp_result:
            self.ip = addr 
        else:
            self.ip += 1 
    
    def call(self, addr):
        self._seq_addr_ok(addr)
        if self.cmp_result:
            self.stack.append((self.ip, self.rep))
            self.ip = addr
        else:
            self.ip += 1
        
    def ret(self):
        if self.cmp_result:
            self.ip, self.rep = self.stack.pop()
        else:
            self.ip += 1
    
    def load_repeat(self, value):
        self.rep = value
        self.ip +=1 
        
    def repeat(self, addr):
        self.rep -= 1
        if self.rep > 0:
            self.goto(addr)
        else:
            self.ip += 1
            
    def load_cmp(self, addr, mask, flag):
        if flag:
            self._vram_addr_ok(addr)
            if self.vram[addr].test_valid():
                self.cmp = self.vram[addr].data
            else:
                self.halt = True
        else:
            raise NotImplementedError("TDM Message queue not yet implemented!")
        self.ip += 1
    
    def compare(self, op, imm):
        self.ip += 1
        
        if op == EQUAL:
            self.cmp_result = (imm == self.cmp)
        elif op == NOTEQUAL:
            self.cmp_result = (imm != self.cmp)
        elif op == GREATERTHAN:
            self.cmp_result = (self.cmp > imm)
        elif op == LESSTHAN:
            self.cmp_result = (self.cmp < imm)
        else:
            raise BadInstruction(f"Unknown comparison code: {op}")        
        
    def custom(self):
        self.ip += 1
        
    def invalidate(self, addr, mask, flag):
        self._vram_addr_ok(addr)
        self.vram[addr].invalidate(mask, flag)
        self.ip += 1
        
    def writeaddr(self, addr, value, flag):
        self._vram_addr_ok(addr)
        self.vram[addr].store(value, flag)    
        self.ip += 1
    
    ### END INSTRUCTIONS #######################
    
    def decode(self):
        if self.ip > len(self.seq_mem)-1:
            print("Exceeded available sequence memory!")
            self.halt = True
            return
            
        instr  = self.seq_mem[self.ip]
        opcode = (instr.header >> 4) & 0xf 
        engine = (instr.header >> 2) & 0x3
        write_flag = instr.header & 0x1
        vram_flag = (instr.payload >> 48) & 0x1
        
        if opcode == WFM:
            N      = (instr.payload >> 24) & 2**21 - 1
            addr   = instr.payload & 2**24 - 1
            ta_bit = (instr.payload >> 45) & 0x1
            self.waveform(addr, N, ta_bit)
            
        elif opcode == MARKER:
            engine = (instr.header >> 2) & 0x3
            count = instr.payload & 2**32 - 1
            state = (instr.payload >> 32) & 0x1
            self.marker(engine, state, count)
        
        elif opcode == WAIT:
            self.wait()
        
        elif opcode == LOAD:
            self.load_repeat(instr.payload)
            
        elif opcode == REPEAT:
            addr = instr.payload & 2**26 - 1
            self.repeat(addr)
            
        elif opcode == CMP:
            op = (instr.payload >> 8) & 0x3
            imm = instr.payload & 0xff
            result = self.compare(op, imm)
            
        elif opcode == GOTO:
            addr = instr.payload & 2**26 - 1
            self.goto(addr)
            
        elif opcode == CALL:
            addr = instr.payload & 2**26 - 1
            self.call()
            
        elif opcode == RET:
            self.ret()
            
        elif opcode == SYNC:
            self.sync()
            
        elif opcode == MODULATION:
            self.modulate()
            
        elif opcode == LOADCMP:
            addr  = instr.payload & 0xFFFF
            value = (instr.payload >> 16) & 0xFFFFFFFF
            self.load_cmp(addr, value, vram_flag)
            
        elif opcode == PREFETCH:
            addr = instr.payload & 2**26 - 1
            self.prefetch(addr)
            
        elif opcode == WRITEADDR:            
            addr  = instr.payload & 0xFFFF
            value = (instr.payload >> 16) & 0xFFFFFFFF 
            
            #test for invalidate
            if write_flag:
                self.writeaddr(addr, value, vram_flag)
            else:
                self.invalidate(addr, value, vram_flag)
                
        elif opcode == NOP:
            self.noop()
            
        else:
            raise BadInstruction(f"Unknown opcode {opcode}")
            
        if write_flag and (opcode == WFM or opcode == MARKER):
            self.wengine.write()
            for engine in self.mengine:
                engine.write()
            
    def run(self):
        step = 0
        while not self.halt:
            self.decode()
            
            step += 1
            if step > self.max_step:
                self.halt = True
                print("Exceeded maximum simulation duration.")
            if step > self.stop:
                self.halt = True
                print("Finished!")
                
        print(f"Sequencer halted at IP = {self.ip}")
        
        
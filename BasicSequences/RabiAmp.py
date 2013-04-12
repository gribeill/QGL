from QGL.PulsePrimitives import *
from QGL.Compiler import compile_to_hardware
from QGL.PulseSequencePlotter import plot_pulse_files

def RabiAmp(qubit, amps, showPlot=False, phase=0):
	"""
	
	Variable amplitude Rabi nutation experiment.

	Parameters
	----------
	qubit : logical channel to implement sequence (LogicalChannel) 
	amps : pulse amplitudes to sweep over (iterable)
	showPlot : whether to plot (boolean)
	phase : phase of the pulse (radians)

	Returns
	-------
	plotHandle : handle to plot window to prevent destruction
	"""
	seqs = [[Utheta(qubit, amp=amp, phase=phase), MEAS(qubit)] for amp in amps]

	fileNames = compile_to_hardware(seqs, 'Rabi/Rabi')
	print(fileNames)

	if showPlot:
		plotWin = plot_pulse_files(fileNames)
		return plotWin



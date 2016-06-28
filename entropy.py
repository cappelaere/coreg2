import math
import numpy
import scipy.stats
from scipy.stats import chi2_contingency

# http://pythonhosted.org/MedPy/_modules/medpy/metric/image.html

#
# 8bit Image Data
#
def ImageProbabilityDistribution(data):
	histogram 			= numpy.histogram(data, bins=256)[0]
	histogram_length 	= sum(histogram)
	samples_probability = [float(h) / histogram_length for h in histogram]
	return samples_probability
	
def Shannon(data):
	samples_probability = ImageProbabilityDistribution(data)
	e		 			= -sum([p * numpy.log2(p) for p in samples_probability if p != 0])
	return e

def MI(data1, data2):
	c_xy = numpy.histogram2d(numpy.asarray(data1)[:,0], numpy.asarray(data2)[:,0], bins=256)[0]
	g, p, dof, expected = chi2_contingency(c_xy, lambda_="log-likelihood")
	mi = 0.5 * g / c_xy.sum()
	return mi
	
def __range(a, bins):
	'''Compute the histogram range of the values in the array a according to
	scipy.stats.histogram.'''
	a = numpy.asarray(a)
	a_max = a.max()
	a_min = a.min()
	s = 0.5 * (a_max - a_min) / float(bins - 1)
	return (a_min - s, a_max + s)
 
def __entropy(data):
	'''Compute entropy of the flattened data set (e.g. a density distribution).'''
	# normalize and convert to float
	data = data/float(numpy.sum(data))
	# for each grey-value g with a probability p(g) = 0, the entropy is defined as 0, therefore we remove these values and also flatten the histogram
	data = data[numpy.nonzero(data)]
	# compute entropy
	return -1. * numpy.sum(data * numpy.log2(data))
	
def MutualInformation(data1, data2, bins=256):
	#e1 		= Shannon(data1)
	#e2 		= Shannon(data2)
	
	i1 = numpy.asarray(data1)
	i2 = numpy.asarray(data2)	
	# validate function arguments
	if not i1.shape == i2.shape:
		raise ArgumentError('the two supplied images must be of the same shape')
	
	# compute i1 and i2 histogram range
	i1_range = __range(i1, bins)
	i2_range = __range(i2, bins)
	
	# compute joined and separated normed histograms
	i1i2_hist, _, _ = numpy.histogram2d(i1.flatten(), i2.flatten(), bins=bins, range=[i1_range, i2_range]) # Note: histogram2d does not flatten array on its own
	i1_hist, _ = numpy.histogram(i1, bins=bins, range=i1_range)
	i2_hist, _ = numpy.histogram(i2, bins=bins, range=i2_range)
	
	# compute joined and separated entropy
	i1i2_entropy = __entropy(i1i2_hist)
	i1_entropy = __entropy(i1_hist)
	i2_entropy = __entropy(i2_hist)
	
	# compute and return the mutual information distance
	return i1_entropy + i2_entropy - i1i2_entropy

# for identical images, kld = 0
# data1: Original Image
# data2: Image we are trying to register
def KullbackLeiblerDivergence(data1, data2):
	p1 = ImageProbabilityDistribution(data1)
	p2 = ImageProbabilityDistribution(data2)
	
	#kld1 = -sum(p1 * numpy.log2(p1/p) for p in p2 if p != 0])
	kld = scipy.stats.entropy(p1,qk=p2,base=2)
	return kld
	
def min_entropy(l):
	return -numpy.log2(max(l))

def Renyi(data, alpha=1):
	samples_probability = ImageProbabilityDistribution(data)
	
	if abs(alpha - 1) < 10**-10:
		return shannon_entropy(l)

	try:
		# "if p>0" saves us from 0**0 trouble.
		return numpy.log2(sum([p**float(alpha) for p in samples_probability if p>0]))/(1-alpha)
	except (ZeroDivisionError, OverflowError):
		print "Renyi error, return min entropy"
		return min_entropy(samples_probability)

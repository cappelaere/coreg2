#!/usr/bin/env python

import os, inspect, sys
import argparse
import math, time

import numpy
import numpy.ma as ma

from scipy import misc

from osgeo import gdal
from osgeo import osr
from osgeo import ogr
import gdalnumeric

# NOTE check https://github.com/mtpatter/eo1-demo/blob/master/classify.py
# http://cegis.usgs.gov/soil_moisture/pdf/A%20Straight%20Forward%20guide%20for%20Processing%20Radiance%20and%20Reflectance_V_24Jul12.pdf

import pgc_config

def calcJDay (date):
    #Separate date aspects into list (check for consistency in formatting of all
    #Landsat7 metatdata) YYYY-MM-DD
    dt = date.rsplit("-")

    #Cast each part of the date as a in integer in the 9 int tuple mktime
    t = time.mktime((int(dt[0]), int(dt[1]), int(dt[2]), 0, 0, 0, 0, 0, 0))

    #As part of the time package the 7th int in mktime is calculated as Julian Day
    #from the completion of other essential parts of the tuple
    jday = time.gmtime(t)[7]

    return jday

# http://lists.osgeo.org/pipermail/gdal-dev/2009-April/020406.html
def calcSolarDist (doy):
	return (1+0.01672 * math.sin(2 * math.pi * (doy - 93.5) / 365))

	
class EO1_ALI:
	def __init__( self, outpath, scene, ext, verb=0 ):	
		self.scene 				= scene
		self.outpath			= outpath
		self.verbose			= verb
		self.ext				= ext	
		self.meta_file			= os.path.join(outpath, scene + "_MTL_" + ext + ".TXT")
		self.getMetaData()	
	
	# At sensor Min/Max radiance	
	def getLMinMax( self, bandNum ) :
		LUM = {
			'b1':	[-2.18, 784.2],		# PAN
			'b2':	[-3.36, 1471],		# 1P
			'b3':	[-4.36, 1405],		# 1
			'b4':	[-1.87, 915.5],		# 2
			'b5':	[-1.28, 588.5],		# 3
			'b6':	[-0.84, 359.6],	    # 4
			'b7':	[-0.641, 297.5],  	# 4P
			'b8':	[-1.29,  270.7],    # 5P
			'b9':	[-0.597, 91.14],    # 5
			'b10':	[-0.209, 29.61]		# 7
		 } 
		   	
		lum = LUM['b'+str(bandNum)]
		if self.verbose:
			print "LUM", bandNum, lum	
		return lum
	
	
	# from Landsat Calibration Summary RSE (Chandler)
	def getESUN(self, bandNum):
		ESUN = { 	
				'b1':	1724,		# PAN
				'b2':	1857,		# 1P
				'b3':	1996,		# 1
				'b4':	1807,		# 2
				'b5':	1536,		# 3
				'b6':	1145, 	    # 4
				'b7':	955.8,  	# 4P
				'b8':	452.3,     	# 5P
				'b9':	235.1,      # 5
				'b10':	82.38 }   	# 7
		esun = ESUN['b'+str(bandNum)]
		if self.verbose:
			print "ESUN", bandNum, esun
		
		return esun

	def execute( self, cmd ):
		if self.verbose:
			print cmd
		os.system(cmd)

	# This should not be used as L1T is already in radiance values, I think
	# Compute radiance from DN
	def radiance(self, band, dn):
		SCALING_FACTOR = 'BAND'+str(band)+"_SCALING_FACTOR"
		SCALING_OFFSET = 'BAND'+str(band)+'_OFFSET'
		
		if self.verbose:
			print 'SCALING_FACTOR', band, self.metadata[SCALING_FACTOR]
			print 'SCALING_OFFSET', band, self.metadata[SCALING_OFFSET]
			
		radiance	= float(self.metadata[SCALING_FACTOR]) * dn + float(self.metadata[SCALING_OFFSET])
		
		if self.verbose:
			lum 	= self.getLMinMax(band)
			min_rad	= numpy.min(radiance)
			max_rad	= numpy.max(radiance)
			print "radiance band:", band, min_rad, numpy.mean(radiance), max_rad
			if min_rad < lum[0]*1.1:
				print "*** Min rad seems too small"
			if max_rad > lum[1]*1.1:
				print "** Max rad seems too big"
			
		return radiance

				
	# Compute Top of Atmosphere Reflectance
	def toa(self, band, radiance, scale=1000.0):
		dt 	= self.metadata['ACQUISITION_DATE']
		jd 	= calcJDay(dt)
		esd	= calcSolarDist(jd)
		
		el	= self.metadata['SUN_ELEVATION']
		za	= (90.0- float(el))
		
		if self.verbose:
			print "Acquisition Date:", dt
			print "Julian Day:", jd
			print "Earth-Sun distance:", esd
			print "Sun Elevation in Deg:", el
			print "Sun Zenith Angle in Deg:", za
		
		# constant = Cos(sun zenith angle) / (pi * (Sun-Earth distance)^2)
		toa_constant = math.cos( za * math.pi/180.0 ) / ( math.pi * esd**2 )
				
		esun 		= self.getESUN(band)
		const		= esun * toa_constant
		
		toa			= scale * radiance / const
		if self.verbose:
			min_toa	= numpy.min(toa)
			max_toa	= numpy.max(toa)
			
			print "TOA band:", band, "min:", numpy.min(toa), "mean:", numpy.mean(toa), "max:", numpy.max(toa)
		
		return toa

	def getMetaData(self):
		f = open(self.meta_file)
		#Create an empty dictionary with which to populate all the metadata fields.
		self.metadata = {}

		#Each item in the txt document is seperated by a space and each key is
		#equated with '='. This loop strips and seperates then fills the dictonary.

		for line in f:
			if not line.strip() == "END":
				val = line.strip().split('=')
				self.metadata [val[0].strip()] = val[1].strip().strip('"')      
			else:
				break
	
	def reproject( self, epsg, in_file, out_file):
		if self.verbose:
			print "reproject ", in_file, " to:", out_file

		# remove out_file if it already exists
		if os.path.isfile(out_file):
			os.remove(out_file)
			
		cmd = "gdalwarp -of GTiff -co COMPRESS=DEFLATE -t_srs "+ epsg +" " + in_file + " " + out_file
		self.execute(cmd)
		
	def get_file_name( self, bandNum):
		if bandNum < 10:
			fileName = os.path.join(self.outpath, self.scene + "_B0" + str(bandNum)+ "_" + self.ext + ".TIF")
		else:
			fileName = os.path.join(self.outpath, self.scene + "_B" + str(bandNum)+ "_" + self.ext + ".TIF")
			
		return fileName
		
	def get_band_data(self, bandNum ):
		
		fileName = self.get_file_name(bandNum)
			
		ds = gdal.Open( fileName )
		if ds is None:
			print 'ERROR: file has no data:', fileName
			sys.exit(-1)

		self.RasterXSize = ds.RasterXSize
		self.RasterYSize = ds.RasterYSize
		self.RasterCount = ds.RasterCount
		
		self.projection  = ds.GetProjection()
		self.geotransform= ds.GetGeoTransform()
		
		band 	= ds.GetRasterBand(1)
		data	= band.ReadAsArray(0, 0, self.RasterXSize, self.RasterYSize )
		
		data[data<0] = 0	# remove edges
		
		if self.verbose:
			print "Loaded Band:", bandNum, "min:", numpy.min(data), "mean:", numpy.mean(data), "max:", numpy.max(data)

		ds 		= None
		return data

	def linear_stretch2(self, data, min_percentile=1.0, max_percentile=97.0):
		data_min 	= float(numpy.min(data[numpy.nonzero(data)]))
		pmin		= numpy.percentile(data[numpy.nonzero(data)],min_percentile)
		pmax		= numpy.percentile(data[numpy.nonzero(data)],max_percentile)
		data	 	= (data - pmin)/(pmax-data_min)
		
		if verbose:
			print min, pmin, pmax
			
		data[data>1]=1
		data *= 255
		return data_scale
	
	
	def linear_stretch(self, data, min_percentile=1.0, max_percentile=97.0):
				
		if self.verbose:
			print 'linear_stretch', numpy.min(data), numpy.mean(data), numpy.max(data), min_percentile, max_percentile

		pmin, pmax = numpy.percentile(data[numpy.nonzero(data)], (min_percentile, max_percentile))
		if self.verbose:
			print "pmin2:", pmin
			print "pmax2:", pmax

		data[data>pmax]=pmax
		data[data<pmin]=pmin
		
			
		bdata = misc.bytescale(data)
		return bdata

	# http://www.janeriksolem.net/2009/06/histogram-equalization-with-python-and.html
	def histeq(self, im,nbr_bins=256):
		"""  Histogram equalization of a grayscale image. """

		# get image histogram
		imhist,bins = numpy.histogram(im.flatten(),nbr_bins,normed=True)
		cdf = imhist.cumsum() # cumulative distribution function
		cdf = 255 * cdf / cdf[-1] # normalize

		# use linear interpolation of cdf to find new pixel values
		im2 = numpy.interp(im.flatten(),bins[:-1],cdf)

		return im2.reshape(im.shape), cdf
				
	def testTOA(self):
		toa = self.get_band_data(10 )
	
	def generate_color_table(self):
		ct = gdal.ColorTable()
		
		ct.SetColorEntry( 0, (0, 0, 0, 0) )

		ct.SetColorEntry( 1, (153, 0, 130, 255) )
		ct.SetColorEntry( 2, (203,24,29, 255) )
		ct.SetColorEntry( 3, (239,59,44,255) )
		ct.SetColorEntry( 4, (251,106,74,255) )
		ct.SetColorEntry( 5, (252,146,114, 255) )
		ct.SetColorEntry( 6, (252,187,161, 255) )
		ct.SetColorEntry( 7, (254,229,217, 255) )
		return ct

	def write_data(self, data, fileName, type=gdal.GDT_Float32, nbands=1, ct=0):
		fileName 	= os.path.join(self.outpath, fileName)
		
		if self.verbose:
			print "write_data", fileName
		
		driver 		= gdal.GetDriverByName( "GTiff" )
		dst_ds 		= driver.Create( fileName, self.RasterXSize, self.RasterYSize, nbands, type, [ 'INTERLEAVE=PIXEL', 'COMPRESS=DEFLATE' ] )
		band 		= dst_ds.GetRasterBand(1)

		band.WriteArray(data, 0, 0)
		band.SetNoDataValue(0)

		if ct :
			if self.verbose:
				print "write ct"
			
			ct = self.generate_color_table()
			band.SetRasterColorTable(ct)
			
		if self.verbose:
			print "write geotransform and projection"
		dst_ds.SetGeoTransform( self.geotransform )
		dst_ds.SetProjection( self.projection )
			
		if self.verbose:
			print "Written", fileName

		dst_ds 		= None
		
if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Get EO-1 ALI data')
	apg_input = parser.add_argument_group('Input')
	apg_input.add_argument("-f", "--force", 	action='store_true', help="Forces new product to be generated")
	apg_input.add_argument("-v", "--verbose", 	action='store_true', help="Verbose on/off")
	apg_input.add_argument("-s", "--scene", 	help="EO-1 Scene")
	apg_input.add_argument("-b", "--band",	 	help="EO-1 Band")


	options 	= parser.parse_args()
	force		= options.force
	verbose		= options.verbose
	scene	 	= options.scene

	outdir		= os.path.join(config.EO1_DIR,scene)	
	scene	 	= options.scene.split("_")[0]
	band		= int(options.band)
	
	app 		= EO1_ALI(outdir, scene, "L1GST", verbose )

	dn 			= app.get_band_data(band)
	radiance  	= app.radiance(band, dn)
	app.write_data(app.linear_stretch(radiance), 'rad_b'+options.band+'.tif', gdal.GDT_Byte, 1, 0)
	
	toa			= app.toa(band, radiance, 1000.0)
	app.write_data(app.linear_stretch(toa), 'refl_b'+options.band+'.tif', gdal.GDT_Byte, 1, 0)
	
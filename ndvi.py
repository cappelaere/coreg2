import os, json, sys, math
import config
from osgeo import gdal
import numpy
from scipy import misc

def get_band_data(band_file ):
	ds = gdal.Open( band_file )
	if ds is None:
		print 'ERROR: file has no data:', band_file
		sys.exit(-1)

	band 	= ds.GetRasterBand(1)
	data	= band.ReadAsArray(0, 0, ds.RasterXSize, ds.RasterYSize )
	ds 		= None
	
	return data

def read_metadata(meta_file):
	print "Reading metadata", meta_file
	
	f = open(meta_file)
	#Create an empty dictionary with which to populate all the metadata fields.
	metadata = {}

	#Each item in the txt document is seperated by a space and each key is
	#equated with '='. This loop strips and seperates then fills the dictonary.

	for line in f:
		if not line.strip() == "END":
			val = line.strip().split('=')
			metadata [val[0].strip()] = val[1].strip().strip('"')      
		else:
			break

	f.close()
	
	return metadata

#http://landsat.usgs.gov/Landsat8_Using_Product.php	
def get_toa_data(dn_data, bandNum, metadata ):	
	mp 			= float(metadata['REFLECTANCE_MULT_BAND_'+str(bandNum)])
	ap			= float(metadata['REFLECTANCE_ADD_BAND_'+str(bandNum)])
	se			= float(metadata['SUN_ELEVATION'])
	
	toa			= (mp * dn_data + ap) / math.sin( se * math.pi/180.0)
	return toa

def linear_stretch( data, min_percentile=1.0, max_percentile=97.0):
			
	pmin, pmax = numpy.percentile(data[numpy.nonzero(data)], (min_percentile, max_percentile))

	data[data>pmax]=pmax
	data[data<pmin]=pmin
	
	bdata = misc.bytescale(data)
	return bdata

def save_data(ndvi_file, output_band, band_file):
	driver 			= gdal.GetDriverByName( "GTiff" )
	src_ds 			= gdal.Open( band_file )
	proj			= src_ds.GetProjection()
	geotransform 	= src_ds.GetGeoTransform()
	
	ds 		= driver.Create( ndvi_file, src_ds.RasterXSize, src_ds.RasterYSize, 1, gdal.GDT_Byte, [ 'COMPRESS=DEFLATE' ] )
	band 	= ds.GetRasterBand(1)
	
	band.WriteArray(output_band, 0, 0)
	
	ds.SetGeoTransform( geotransform )
	ds.SetProjection( proj )
	
	print "Saved", ndvi_file
	src_ds 	= None
	ds 		= None
	
def process(entityID):
	print "NDVI...", entityID
	
	year 		= entityID[9:13]
	doy			= entityID[13:16]
	l8_dir		= os.path.join(config.LANDSAT8_DIR, year, doy)

	dst_dir 	= os.path.join(l8_dir, entityID)
	bqa_file	= os.path.join(dst_dir, entityID + "_BQA.TIF")
	meta_file	= os.path.join(dst_dir, entityID + "_MTL.txt")
	ndvi_file	= os.path.join(dst_dir, entityID + "_NDVI.TIF")
	
	if not os.path.exists(ndvi_file):
		metadata 	= read_metadata(meta_file)
		#bqa_data	= get_band_data(bqa_file)	
	
		# cloud mask
		#cloud_mask			= (bqa_data & 0xC000) == 0xC000
		#cirrus_mask			= (bqa_data & 0x3000) == 0x3000
		#no_data				= (bqa_data & 0x1) == 0x1

		#bqa_data[cloud_mask] 	= 1
		#bqa_data[cirrus_mask] 	= 1
		#bqa_data[no_data] 		= 0
		
		b4_file		= os.path.join(dst_dir, entityID + "_B4.TIF")
		b4_data		= get_band_data(b4_file)
		b4_toa_data	= get_toa_data(b4_data, 4, metadata)

		b5_file		= os.path.join(dst_dir, entityID + "_B5.TIF")
		b5_data		= get_band_data(b5_file)
		b5_toa_data	= get_toa_data(b5_data, 5, metadata)
	
		calc_band 	= numpy.true_divide((b5_toa_data - b4_toa_data), (b5_toa_data + b4_toa_data))

		# This is the trick to keep the nodata = 0
		output_band = numpy.rint((calc_band + 1) * 255 / 2).astype(numpy.uint8)
		output_band[b4_data==0] = 0
		output_band[b5_data==0] = 0
		
		#output_band = linear_stretch(output_band)
		
		save_data(ndvi_file, output_band, b5_file)
	
def convert_rgb_to_grayscale(infile, outfile):
	src_ds 			= gdal.Open( infile )
	proj			= src_ds.GetProjection()
	geotransform 	= src_ds.GetGeoTransform()
	
	red_band 		= src_ds.GetRasterBand(1)
	red_data		= red_band.ReadAsArray(0, 0, src_ds.RasterXSize, src_ds.RasterYSize )
	
	green_band 		= src_ds.GetRasterBand(2)
	green_data		= green_band.ReadAsArray(0, 0, src_ds.RasterXSize, src_ds.RasterYSize )
	
	blue_band 		= src_ds.GetRasterBand(3)
	blue_data		= blue_band.ReadAsArray(0, 0, src_ds.RasterXSize, src_ds.RasterYSize )
	
	grey			= (0.299*red_data + 0.587*green_data + 0.114*blue_data)

	driver 			= gdal.GetDriverByName( "GTiff" )
	ds 				= driver.Create( outfile, src_ds.RasterXSize, src_ds.RasterYSize, 1, gdal.GDT_Byte, [ 'COMPRESS=DEFLATE' ] )
	band 			= ds.GetRasterBand(1)
	
	band.WriteArray(grey, 0, 0)
	
	ds.SetGeoTransform( geotransform )
	ds.SetProjection( proj )
	ds				= None
	src_ds			= None
	
	print "Saved", outfile
	
	
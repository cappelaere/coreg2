#
# EO-1 Scene Co-registration Workflow
#
import os, inspect, sys, math, time, glob, io, pprint, datetime
import config
import argparse
import json, geojson

from osgeo import gdal
from usgs import api

import chip, eo1, search, coreg

verbose 	= 0

pp 			= pprint.PrettyPrinter(indent=4)

def execute( cmd ):
	if verbose:
		print cmd
	os.system(cmd)
	
def SaveImage(fileName, ds, data):

	if verbose:
		print "**Saving to", fileName
	
	# Save it as Byte, compressed
	driver 		= gdal.GetDriverByName( "GTiff" )
	ods			= driver.Create( fileName, ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte,	[ 'COMPRESS=DEFLATE' ] )
	oband 		= ods.GetRasterBand(1)
	oband.WriteArray(data, 0, 0)
	ods.SetGeoTransform( ds.GetGeoTransform() )
	ods.SetProjection( ds.GetProjection() )
	ods 		= None
	
def SaveRGBImage(fileName, ds, r_data,g_data,b_data):

	if verbose:
		print "**Saving to", fileName
	
	# Save it as Byte, compressed
	driver 		= gdal.GetDriverByName( "GTiff" )
	ods			= driver.Create( fileName, ds.RasterXSize, ds.RasterYSize, 3, gdal.GDT_Byte,	[ 'COMPRESS=DEFLATE' ] )
	
	ods.GetRasterBand(1).WriteArray(r_data, 0, 0)
	ods.GetRasterBand(2).WriteArray(g_data, 0, 0)
	ods.GetRasterBand(3).WriteArray(b_data, 0, 0)
	
	
	ods.SetGeoTransform( ds.GetGeoTransform() )
	ods.SetProjection( ds.GetProjection() )
	ods 		= None
	
#
# Compute Center Target form Metadata 
#
def GetCenterTarget(metadata, solution):
	
	UL_CORNER_LAT 	=  float(metadata['PRODUCT_UL_CORNER_LAT'])
	UL_CORNER_LON	=  float(metadata['PRODUCT_UL_CORNER_LON'])
	UR_CORNER_LAT	=  float(metadata['PRODUCT_UR_CORNER_LAT'])
	UR_CORNER_LON	=  float(metadata['PRODUCT_UR_CORNER_LON'])
	
	LL_CORNER_LAT 	=  float(metadata['PRODUCT_LL_CORNER_LAT'])
	LL_CORNER_LON	=  float(metadata['PRODUCT_LL_CORNER_LON'])
	LR_CORNER_LAT	=  float(metadata['PRODUCT_LR_CORNER_LAT'])
	LR_CORNER_LON	=  float(metadata['PRODUCT_LR_CORNER_LON'])
	
	LM_LON			= (UL_CORNER_LON + LL_CORNER_LON) / 2.
	LM_LAT			= (UL_CORNER_LAT + LL_CORNER_LAT) / 2.
	
	RM_LON			= (UR_CORNER_LON + LR_CORNER_LON) / 2.
	RM_LAT			= (UR_CORNER_LAT + LR_CORNER_LAT) / 2.
	
	centerLat		= (LM_LAT + RM_LAT) / 2.
	centerLon		= (LM_LON + RM_LON) / 2.
	
	if verbose:
		print "centerTarget", centerLat, centerLon
	
		#kml = "<?xml version='1.0' encoding='UTF-8'?>\n" 
		#kml += "<kml xmlns='http://earth.google.com/kml/2.0'> <Document>"
		#kml += "<Style id='PolyStyle'><LabelStyle><color>ff0000cc</color></LabelStyle><LineStyle><width>1.5</width><color>ff0000ff</color></LineStyle></Style>"

		#kml += "<Placemark><name>EO1Scene</name>\n"
		#kml += "<styleUrl>#PolyStyle</styleUrl>\n"
	
		#kml += "<Polygon>\n"
		#kml += "<outerBoundaryIs><LinearRing>\n"
		#kml += "<coordinates>\n"
		
		#kml += str(UL_CORNER_LON) + "," + str(UL_CORNER_LAT) + ",0\n"
		#kml += str(UR_CORNER_LON) + "," + str(UR_CORNER_LAT) + ",0\n"
		#kml += str(LR_CORNER_LON) + "," + str(LR_CORNER_LAT) + ",0\n"
		#kml += str(LL_CORNER_LON) + "," + str(LL_CORNER_LAT) + ",0\n"
		#kml += str(UL_CORNER_LON) + "," + str(UL_CORNER_LAT) + ",0\n"
				
		#kml += "</coordinates></LinearRing></outerBoundaryIs></Polygon>\n"
	
		#kml += "</Placemark>\n"

		#kml += "</Document></kml>"
		#kml_filename = os.path.join(base_dir, "scene.kml")
		#with io.open(kml_filename, 'w', encoding='utf-8') as f:
		#	f.write(unicode(kml))
	
	solution['centerLat'] = centerLat
	solution['centerLon'] = centerLon

def MakePolygon( ndvi_4326_FileName ):
	base_dir			= os.path.dirname(ndvi_4326_FileName)
	footstepsFileName 	= os.path.join(base_dir, "footsteps.tif")
	geojsonDir			= os.path.join(base_dir,"geojson")

	if os.path.exists( footstepsFileName ):
		return
		
	ds 					= gdal.Open( ndvi_4326_FileName )
	projection  		= ds.GetProjection()
	geotransform		= ds.GetGeoTransform()
	#band				= ds.GetRasterBand(1)
		
	xorg				= geotransform[0]
	yorg  				= geotransform[3]
	xres				= geotransform[1]
	yres				= -geotransform[5]
	xmax				= xorg + geotransform[1]* ds.RasterXSize
	ymax				= yorg + geotransform[5]* ds.RasterYSize
	
	band		 		= ds.GetRasterBand(1)

	data				= band.ReadAsArray(0, 0, ds.RasterXSize, ds.RasterYSize )
	data[data>0]		= 255					
	
	if not os.path.exists(geojsonDir):            
		os.makedirs(geojsonDir)
	
	SaveImage(footstepsFileName, ds, data)
	ds 					= None
	
	cmd = "gdal_translate -q -of PNM " + footstepsFileName + " "+footstepsFileName+".pgm"
	execute(cmd)
	
	cmd = str.format("potrace -i -z black -a 1.5 -t 3 -b geojson -o {0} {1} -x {2} -L {3} -B {4} ", footstepsFileName+".geojson", footstepsFileName+".pgm", xres, xorg, ymax ); 	
	execute(cmd)
	
	cmd = str.format("topojson -o {0} --simplify-proportion 0.999 {1}", footstepsFileName+".topojson", footstepsFileName+".geojson");
	execute(cmd)
	
	cmd = "topojson-geojson --precision 6 -o %s %s" % ( geojsonDir, footstepsFileName+".topojson" )
	execute(cmd)
	
#
# Make an EO-1 product in EPSG:4326
#
def	MakeEO1Product(solution):
	scene		= solution['eo1Scene']
	
	year		= scene[10:14]
	doy			= scene[14:17]
	base_dir	= os.path.join(config.ALI_DIR, year, doy, scene)
	eo1_ali 	= eo1.EO1_ALI(base_dir, scene, "L1T", verbose )

	solution['base_dir']	= base_dir
	
	GetCenterTarget(eo1_ali.metadata, solution)
	
	if solution['reference'] == 'ndvi':
		ndviFileName 		= os.path.join(base_dir, "ndvi.tif")
		ndvi_4326_FileName 	= os.path.join(base_dir, "ndvi_4326.tif")

		solution['eo1InputFilename'] 	= ndvi_4326_FileName	
	
	
		if os.path.exists(ndvi_4326_FileName):
			return ndvi_4326_FileName
		
		print "Making NDVI for", scene

		b5			= eo1_ali.get_band_data(5)
		b5_rad		= eo1_ali.radiance(5, b5)
		b5_toa		= eo1_ali.toa(5, b5_rad, 1000.)

		b7			= eo1_ali.get_band_data(7)
		b7_rad		= eo1_ali.radiance(7, b7)
		b7_toa		= eo1_ali.toa(7, b7_rad, 1000.)
	
		# Generate NDVI
		epsilon		= 0.1	# to avoid divide by zero
		ndvi 		= (b7_toa - b5_toa) / (b7_toa + b5_toa + epsilon)
	
		eo1_ali.write_data(eo1_ali.linear_stretch(ndvi), 'ndvi.tif', gdal.GDT_Byte, 1, 0)
		eo1_ali.reproject("EPSG:4326", ndviFileName, ndvi_4326_FileName)

	if solution['reference'] == '742':
		ndviFileName 					= os.path.join(base_dir, "bands_10.5.3.tif")
		ndvi_4326_FileName 				= os.path.join(base_dir, "bands_10.5.3_4326.tif")
		solution['eo1InputFilename'] 	= ndvi_4326_FileName	

		if os.path.exists(ndvi_4326_FileName):
			return ndvi_4326_FileName

		b10			= eo1_ali.get_band_data(10)
		b10_rad		= eo1_ali.radiance(10, b10)
		b10_toa		= eo1_ali.toa(10, b10_rad, 1000.)

		b5			= eo1_ali.get_band_data(5)
		b5_rad		= eo1_ali.radiance(5, b5)
		b5_toa		= eo1_ali.toa(5, b5_rad, 1000.)

		b3			= eo1_ali.get_band_data(3)
		b3_rad		= eo1_ali.radiance(3, b3)
		b3_toa		= eo1_ali.toa(3, b3_rad, 1000.)

		fileName	= eo1_ali.get_file_name(3)
		ds			= gdal.Open(fileName)
		
		b10_toa[b5==0] = 0
		b10_toa[b3==0] = 0

		b5_toa[b10==0] = 0
		b5_toa[b3==0] = 0

		b3_toa[b10==0] = 0
		b3_toa[b5==0] = 0
		
		gray = (0.299*b10_toa + 0.587*b5_toa + 0.114*b3_toa)
		SaveImage(ndviFileName, ds, gray)
		eo1_ali.reproject("EPSG:4326", ndviFileName, ndvi_4326_FileName)
		
		#SaveRGBImage(ndviFileName, ds, b10_toa, b5_toa, b3_toa)
		#eo1_ali.reproject("EPSG:4326", ndviFileName, ndvi_4326_FileName)

		ds = None


	MakePolygon(ndvi_4326_FileName)
	
	
#
# Start Coregistration Process
#
def coregister(eo1Scene, entities, zoomLevel, usgs_user, usgs_pass, verbose, reference):
	
	startTime		= datetime.datetime.now()
	solution = {
		'start-time': 		str(startTime),
		'eo1Scene': 		eo1Scene,
		'verbose': 			verbose,
		'zoomLevel':		zoomLevel,
		'usgs_pass': 		usgs_pass,
		'usgs_user':		usgs_user,
		'entities':			entities,
		'reference': 		reference,		#'742',			#ndvi
		'status': 			'FAILED'
	}
	
	
	# We should really have an EO-1 Atmospherically corrected scene but will use ALI_l1G and to Top of Atmosphere correction, then generate an NDVI
	#[EO1_NDVI_fileName, centerLat, centerLon] 	= MakeEO1NDVI(eo1Scene)
	MakeEO1Product(solution)
	
	# Let's find best L8 scene(s)
	search.aws(solution)
	
	# Find Best chip for co-registration
	chip.FindBest(solution)
	
	coreg.apply( solution)
	
	endTime						= datetime.datetime.now()
	deltaTime					= endTime - startTime
	solution['end-time'] 		= str(endTime)
	solution['elapsed-time'] 	= str(deltaTime)
	
	return solution
	
if __name__ == "__main__":
	
	parser 				= argparse.ArgumentParser(description='Process Co-Registration')
	apg_input 			= parser.add_argument_group('Input')

	apg_input.add_argument("-f", "--force", 	action='store_true', help="Forces new product to be generated")
	apg_input.add_argument("-v", "--verbose", 	action='store_true', help="Verbose on/off")
	apg_input.add_argument("-s", "--scene", 	help="Scene")
	apg_input.add_argument("-z", "--zoom", 		help="ZoomLevel")

	options 			= parser.parse_args()

	
	# 21 colorado??								EO1A0350402016136110K2	LC80350402016164LGN00 tx= 62, ty= -219
	# 23 Israel Spill							EO1A1740392016134110K8	LC81740392016114LGN00 tx= 97, ty= -356
	# 27 Israel Spill							EO1A1740392016131110K5	LC81740392016114LGN00 tx= 115, ty= -439
	# 31 Israel Spill							EO1A1740392016128110K7	LC81740392016114LGN00 tx= -31, ty= 165
	# 40 Israel Spill							EO1A1740392016123110K8	LC81740392016114LGN00 tx= 24, ty= -94
	# 45 Israel Spill							EO1A1740392016120110K6	LC81740392016114LGN00 tx= 44, ty= -164

	# 24 Voyagers Natl Park 					EO1A1400262016133110K2 	LC81400262015209LGN00 zoom: 10, tx: 109, ty: -331, rmse: 0.003574	
	# 25 Ft McMurray 							EO1A0420202016132110KF	LC80420202015274LGN00 zoom: 10, tx: 188, ty: -321, rmse: 0.005552	
	# 29 Doi Inthanon Thailand					EO1A1310472016129110T2	LC81310472016069LGN00 zoom: 11, tx: -39, ty: 192, rmse: 0.00437
	# 43 Doi Inthanon Thailand					EO1A1310472016121110T1	LC81310472016069LGN00 zoom: 11, tx: 35, ty: -145, rmse: 0.00437
	# 37 Xilinhot grassland 					EO1A1240302016125110TA	LC81240302016148LGN00 zoom: 11, tx: -1, ty: 18, rmse: 0.0397
	# 39 Alaska2								EO1A0710172016123110K4	LC80710172015013LGN00 (Failed)
	#														LC80710172015029LGN00 (Failed)
	# 41 Sarcheshmeh Copper						EO1A1610392016123110KF	LC81610392015308LGN00 zoom: 11, tx: 18, ty: -91, rmse: 0.012808
	# 42 Lake Frome								EO1A0970812016122110K1	LC80970812016135LGN00 zoom: 11, tx: 36, ty: -128, rmse: 0.006667
	
	# Cheated to select right landsat tile and right subtile to find island
	# 22 Nassau Bahamas							EO1A0130422016135110PF  LC80130432014116LGN00 zoom: 11, tx: 72, ty: -279, rmse: 0.003991
	# 26 Nassau Bahamas							EO1A0130422016132110KF  LC80130432014116LGN00 zoom: 11, tx: 76, ty: -405, rmse: 0.003991		Still looks a little off but not much image of the island on this scene
	# 32 Nassau Bahamas							EO1A0130422016127110KF  LC80130432014116LGN00 zoom: 11, tx: -23, ty: 160, rmse: 0.006442
	
	# 28-May 	Pinnacles_Desert_West [MSO/E2] 	EO1A1130812016149110K9	LC81130812015260LGN00	zoom:11, tx:12, ty: -34, rmse:0.035368, algo: SURF
	# 06-15 	Pinnacles_Desert				EO1A1130812016167110K6	LC81130812015260LGN00	zoom:11, tx: 60 ty: -371 rmse: 0.003130, algo: SURF
	# 13-Jun	Coleman Fire					EO1A0430352016165110K0	[LC80440352015064LGN00,LC80430352014134LGN00] zoom:11, tx: 27 ty: -136 rmse: 0.016088, algo: SURF
	
	# 12-Jun	Guanica_Center 					EO1A0050472016164110K0 ['LC80050482014332LGN00'] zoom: 11, tx=48, ty=-153, rmse=0.015041, algo: SIFT
	# 7-Jun		Kern_River						EO1A0420352016159110KH ['LC80420362015322LGN00'] zoom: 11, tx=23, ty=-59, rmse=0.010060, algo: SIFT
	# 5-Jun		Valencia Spain					EO1A1990322016157110K2 ['LC81990332015158LGN00'] zoom: 11, tx=20, ty=-44, rmse=0.025832, algo: ORB
	#			Kern_River_Oil_field [MSO/E2]	EO1A0420352016156110KJ ['LC80420352015194LGN00', 'LC80420362015322LGN00'] zoom: 11, tx=13, ty=-60, rmse=0.010550, algo: SIFT
	#			Christchurch NZ ALI [MSO/E]		EO1A0730902016156110K8 ['LC80730902015283LGN00'] zoom: 11, tx=20, ty=-140, rmse=1.114283, algo: SURF
	#			Tomakomai National Forest		EO1A1070302016156110T6 ['LC81080302015145LGN00', 'LC81070312015138LGN00'] zoom: 11, tx=12, ty=-126, rmse=0.008347, algo: SIFT
	
	# 			Uniform Radiance 1 [Brakke/N]	EO1A1770452016156110PP ['LC81770452016167LGN00'] zoom: 11, FAILED
	
	# 			SWE-sfrye-5275-20160603-bima... EO1A1780222016156110KF ['LC81790222014255LGN00', 'LC81780232014264LGN00', 'LC81780222014264LGN00', 'LC81770232014209LGN00', 'LC81770222014209LGN00'] zoom: 11, tx=24, ty=-48, rmse=0.019700, algo: SURF
	#			Brazil fire [Brakke/W]			EO1A2240692016156110KF ['LC82240692015269LGN00'] zoom: 11, tx=13, ty=-23, rmse=0.048986, algo: SURF
	#			Dunhuang China HYP [MSO/E]		EO1A1370322016157110T8 ['LC81370322015220LGN00', 'LC81380322015131LGN00'] zoom: 11, tx=13, ty=-60, rmse=0.020442, algo: SURF
	
	# 143-145
	#			Okuma A [MSO/N]					EO1A1070342016143110K2 ['LC81070342013260LGN00', 'LC81060342015131LGN00'] zoom: 11, tx=65, ty=-195, rmse=0.005859, algo: SIFT
	#  			Dinghushan  China [MSO/N] 		EO1A1230442016144110T2  ['LC81220442015291LGN00', 'LC81230442015106LGN00'] zoom: 11, tx=40, ty=-143, rmse=0.007415, algo: SIFT
	#			Oman_Archaeology_2 [MSO/W2]		EO1A1590432016145110K0 ['LC81590432016073LGN00', 'LC81590442016153LGN00'] zoom: 11, tx=1, ty=-19, rmse=0.0857, algo: SURF
	
	# 			Dripsey [MSO/W2]				EO1A2070242016145110T1  ['LC82070232016153LGN00','LC82060242015111LGN00','LC82080232015109LGN00','LC82070242016153LGN00','LC82060232015111LGN00'] zoom: 11, tx=2, ty=14, rmse=0.065585, algo: SIFT
	# 			Brazil fire [Brakke/W]			EO1A2240692016145110KF  ['LC82240692015269LGN00'] zoom: 11, tx=10, ty= -6, rmse: 0.385733, algo: SIFT`
	
	eo1Scene			= "EO1A1770452016156110PP"
	
	# Landsat tiles to use.  Could be more than one.
	entities			= []	
	
	zoomLevel			= options.zoom or 11
	verbose				= options.verbose or 1
	
	# Optional to get access to USGS repo if Amazon fails
	usgs_user			= os.environ['USGS_ACCOUNT'] or None
	usgs_pass			= os.environ['USGS_PASSWORD'] or None
	
	# Reference product to use
	reference			= 'ndvi'	# or 742
	
	solution 			= coregister(eo1Scene, entities, zoomLevel, usgs_user, usgs_pass, verbose, reference)
	
	if solution['status'] == 'SUCCESS':
		result = "Status: %s, %s %s zoom: %s, tx=%s, ty=%d, rmse=%f, algo: %s" %( solution['status'], solution['eo1Scene'], solution['entities'], solution['zoomLevel'], solution['tx'], solution['ty'], solution['rmse'], solution['algo'] )
		print result
	else:
		
		# NOTE: If it fails, you can try with a lower zoom level (10?) or use a different reference product such as 742 (bands used)
		
		pp.pprint(solution['status'])
	
import os, json, sys
import config
import tarfile
import ndvi
import landsat.landsat as landsat
from landsat.landsat import Search, Downloader, Simple

s = Search()

def download( entityID, solution):
	year 		= entityID[9:13]
	doy			= entityID[13:16]
	bands		= ['2', '4', '5', '7', 'QA', 'MTL']
	
	l8_dir		= os.path.join(config.LANDSAT8_DIR, year, doy)
	tgz			= os.path.join(l8_dir, entityID+".tar.bz")
	dst_dir 	= os.path.join(l8_dir, entityID)
	
	usgs_user	= solution['usgs_user']
	usgs_pass	= solution['usgs_pass']
	
	if not os.path.exists(dst_dir):

		print "Downloading", entityID, "to", l8_dir
		d 		= Downloader(download_dir=l8_dir, usgs_user=usgs_user, usgs_pass=usgs_pass)
		scenes 	= [entityID]
	
		print "Downloading", scenes
		d.download(scenes, bands=bands)
	
		if not os.path.exists(dst_dir) and os.path.exists(tgz):
			print "Unzipping", tgz, " stand by..."
			tar = tarfile.open(tgz, 'r')
			tar.extractall(path=dst_dir)
			tar.close()

	if solution['reference'] == 'ndvi':
		ndvi.process(entityID)
		solution['reference_ext'] = '_NDVI.TIF'
	else:
		rgbFileName 	= os.path.join(dst_dir, entityID, entityID+"_bands_742.TIF")
		greyFileName 	= os.path.join(dst_dir, entityID, "..", entityID+"_bands_742.TIF")
		solution['reference_ext'] = '_bands_742.TIF'
		
		if not os.path.exists(rgbFileName):
			print "Process L8 image", rgbFileName
 			p = Simple(dst_dir, bands=[7,4,2], dst_path=dst_dir, verbose=solution['verbose'])
			p.run()
		
		# we need to convert that newly created file to grayscale
		if not os.path.exists(greyFileName):
			ndvi.convert_rgb_to_grayscale(rgbFileName, greyFileName)
			
def find(centerLat,centerLon, limit, cloud_max ):
	output = s.search(lat=centerLat,lon=centerLon, limit=limit, cloud_max=cloud_max, geojson=1)
 	#print "aws search", json.dumps(output, sort_keys=True, indent=4)
	
	entities	= {}
	
	for feature in output['features']:
		pathrow	= feature['properties']['sceneID'][3:9]
		if verbose:
			print feature['properties']['sceneID'],feature['properties']['cloud'],feature['properties']['date'], pathrow
		
		if not (pathrow in entities):
			entities[pathrow] = feature
		else:
			if feature['properties']['cloud'] < entities[pathrow]['properties']['cloud']:
				entities[pathrow] = feature
	
	entity_list = []
	print "check entities"
	for e in entities:
		#print e
		el = entities[e]
		#print el
		print "Found best:", el['properties']['sceneID'], el['properties']['cloud'], el['properties']['date']	#json.dumps(r, sort_keys=True, indent=4)
		entity_list.append(str(el['properties']['sceneID']))
		
	return entity_list
	
#def aws(scene, centerLat, centerLon, _verbose, usgs_user, usgs_pass):
def aws(solution):
	global verbose 
	
	# We already have the landsat tiles
	if len(solution['entities']) > 0 : 
		return
	
	verbose 	= solution['verbose']
	centerLat	= solution['centerLat']
	centerLon	= solution['centerLon']
	
	cloud_max 	= 5
	limit		= 20
	
	ULLat 	= centerLat + 0.1
	ULLon	= centerLon - 0.1
	
	LLLat	= centerLat - 0.1
	LLLon	= centerLon - 0.1
	
	ULLon	= centerLon - 0.1
	ULLat	= centerLat + 0.1
	
	URLon	= centerLon + 0.1
	URLat	= centerLat + 0.1	
	
	entities = []
	
 	el 	= find(ULLat,ULLon, limit, cloud_max )
	for r in el:
		if not (r in entities):
			entities.append(r)
	
	el 	= find(LLLat,LLLon, limit, cloud_max )
	for r in el:
		if not (r in entities):
			entities.append(r)

	el	= find(ULLat,ULLon, limit, cloud_max )
	for r in el:
		if not (r in entities):
			entities.append(r)

	el	= find(URLat,URLon, limit, cloud_max )
	for r in el:
		if not (r in entities):
			entities.append(r)
		
	print entities
	
	for entityID in entities:	
		# Check if the scene exists or needs to be download
		download(entityID, solution)
				
	if len(entities) == 0:
		print "Could not find any landsat tiles.... Grrrr!"
		sys.exit(-1)
	
	solution['entities'] = entities
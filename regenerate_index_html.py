from osgeo import gdal, ogr
import glob
import os
import json
import subprocess

cdn_url = 'https://cdn.proj.org'

agency_list = json.loads(open('AGENCY.json','rt').read())
agencies = {}
for item in agency_list:
    agencies[item['id']] = item


dirnames = []
links = []
for dirname in glob.glob('*'):
    if not os.path.isdir(dirname):
        continue
    dirnames.append(dirname)

gj_ds = ogr.GetDriverByName('GeoJSON').CreateDataSource('files.geojson')
lyr = gj_ds.CreateLayer('files')
lyr.CreateField(ogr.FieldDefn('url', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('name', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('area_of_use', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('type', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('source', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('source_country', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('source_id', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('source_url', ogr.OFTString))
lyr.CreateField(ogr.FieldDefn('description', ogr.OFTString))

total_size = 0
set_files = set()
for dirname in sorted(dirnames):
    if '_' not in dirname:
        continue
    filenames = []
    readme_filename = None
    for f in glob.glob(dirname + '/*'):
        f = os.path.basename(f)
        if f.startswith('README'):
            assert not readme_filename
            readme_filename = f
        else:
            filenames.append(f)

    title = '%s' % (dirname)
    try:
        agency = agencies[dirname]
        title = '<a href="%s">%s</a>' % (agency['url'].replace('&', "&amp;"), agency['agency'])
    except KeyError:

        pass

    links.append('</ul><hr><h3>%s</h3><ul>' % title )
    for f in [readme_filename] + sorted(filenames):

        assert f not in set_files
        set_files.add(f)

        full_filename = os.path.join(dirname, f)
        ds = gdal.OpenEx(full_filename)
        desc = ''
        area_of_use = ''
        if ds:
            imageDesc = ds.GetMetadataItem('TIFFTAG_IMAGEDESCRIPTION')
            if imageDesc:
                pos = imageDesc.find('. Converted from')
                if pos >= 0:
                    imageDesc = imageDesc[0:pos]
                desc = imageDesc

            feat = ogr.Feature(lyr.GetLayerDefn())
            feat['url'] = cdn_url + '/' + f
            feat['name'] = f
            type = ds.GetMetadataItem('TYPE')
            if type:
                feat['type'] = type
            area_of_use = ds.GetMetadataItem('area_of_use')
            if area_of_use:
                feat['area_of_use'] = area_of_use
            feat['source'] = agency['agency']
            feat['source_country'] = agency['country']
            feat['source_id'] = agency['id']
            feat['source_url'] = agency['url']
            if imageDesc:
                feat['description'] = imageDesc
            gt = ds.GetGeoTransform()
            xmin = gt[0] + 0.5 * gt[1]
            ymax = gt[3] + 0.5 * gt[5]
            xmax = xmin + gt[1] * (ds.RasterXSize - 1)
            ymin = ymax + gt[5] * (ds.RasterYSize - 1)

            subds_list = ds.GetSubDatasets()
            if subds_list:
                for subds_name, _ in subds_list:
                    ds = gdal.Open(subds_name)
                    gt = ds.GetGeoTransform()
                    xmin_subds = gt[0] + 0.5 * gt[1]
                    ymax_subds = gt[3] + 0.5 * gt[5]
                    xmax_subds = xmin_subds + gt[1] * (ds.RasterXSize - 1)
                    ymin_subds = ymax_subds + gt[5] * (ds.RasterYSize - 1)
                    xmin = min(xmin, xmin_subds)
                    ymin = min(ymin, ymin_subds)
                    xmax = max(xmax, xmax_subds)
                    ymax = max(ymax, ymax_subds)

            geom = ogr.Geometry(ogr.wkbPolygon)
            ring = ogr.Geometry(ogr.wkbLinearRing)
            ring.AddPoint_2D(xmin, ymin)
            ring.AddPoint_2D(xmin, ymax)
            ring.AddPoint_2D(xmax, ymax)
            ring.AddPoint_2D(xmax, ymin)
            ring.AddPoint_2D(xmin, ymin)
            geom.AddGeometry(ring)
            feat.SetGeometry(geom)
            lyr.CreateFeature(feat)

        size_str = ''
        size = os.stat(full_filename).st_size
        total_size += size
        if size > 1024 * 1024:
            size_str = '. Size: %.1f MB' % (size / (1024. * 1024))

        if f.startswith('README'):
            last_modified = ''
        else:
            p = subprocess.run(['git','log','-1','--pretty=format:%cd','--date=short',full_filename], check=True, stdout=subprocess.PIPE)
            last_modified = '. Last modified: ' + p.stdout.decode('ascii')

        if area_of_use:
            area_of_use = ' - ' + area_of_use
        else:
            area_of_use = ''

        if desc:
            desc = ' - ' + desc
        else:
            desc = ''

        links.append('<li><a href="%s">%s</a>%s%s%s%s</li>' % (f, f, area_of_use, desc, size_str, last_modified))

total_size_str = '%d MB' % (total_size // (1024 * 1024))

content = '<!-- This is a generated file by regenerate_index_html.py. Do not modify !!!! Modify index.html.in instead if you need to make changes-->\n\n'
content += open('index.html.in', 'rt').read().replace('${LINKS_WILL_BE_ADDED_HERE_BY_REGENERATE_INDEX_HTML}', '\n'.join(links)).replace('${TOTAL_SIZE}', total_size_str)
open('index.html', 'wt').write(content)

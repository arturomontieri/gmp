#!/usr/bin/python
#
###########################################################
#                                                         #
# Project: GMP                                            #
# Author:  gianluca.sabella@gmail.com                     #
#                                                         #
# Module:  pluginDhus.py                                  #
# First version: 26/08/2014                               #
#                                                         #
###########################################################

## @package pluginDhus
# This module make a spacialization of the generic pluginClass for the DHUS

prjName='gmp'
APPID  ='pluginDhus'
#currDir=os.getcwd()
import os,sys
thisFolder=os.path.dirname(__file__)
prjFolder=os.path.split(thisFolder)[0]
sys.path.append(prjFolder+'/lib')
from lxml import etree
import pluginClass
import dbif
import libQueue
import httplib, urllib
import config
import base64
import string
import datetime
import pprint
import json
import traceback
import time
import re
import libProduct

#config
#host     = config.ini.get(APPID,'host')
#protocol = config.ini.get(APPID,'protocol')
#port     = config.ini.get(APPID,'port')
#username = config.ini.get(APPID,'username')
#password = config.ini.get(APPID,'password')
url      = config.ini.get(APPID,'url')
urlmeta  = config.ini.get(APPID,'urlmeta')
agent    = config.ini.get(APPID,'agent')
metadatafile=config.getPath(APPID,'metadatafile')
resourcefile=config.getPath(APPID,'resourcefile')
dhusMetadataRepository=config.getPath(APPID,'dhusmetadatarepository')
maxDayLoop=int(config.ini.get(APPID,'maxDayLoop'))
configStartCatalogueDate=config.ini.get(APPID,'StartCatalogueDate')

debug    = True

## gmpPluginDhus class
# It is a specialization of the generic pluginClass
class gmpPluginDhus(pluginClass.gmpPlugin):
    
    ## The constructor
    def __init__(self,connection):
        if not libQueue.checkConnectionParameters(connection):
            raise "connection object was not valid"
        self.id      =connection['id']
        self.type    =connection['type']
        assert self.type=='dhus'
        self.username=connection['username']
        self.password=connection['password']
        self.protocol=connection['protocol']
        self.port    =connection['port']
        self.host    =connection['host']
        
        self.plan=list()
        auth = base64.encodestring('%s:%s' % (self.username, self.password)).replace('\n', '')
        self.headers = { 'Authorization' : 'Basic %s' %  auth }
        if self.protocol=='http':
            self.conn = httplib.HTTPConnection(self.host,self.port)
        if self.protocol=='https':
            self.conn = httplib.HTTPSConnection(self.host,self.port)
        #print self.__dict__
        
    ## Ovverride of the generic downloadPlan function
    # @param self The object pointer
    # @return plan a list of dictionary for each item to be downloaded
    def getPlan(self):
        #take the last execution time to be used as reference for the new query
        try:
            self.res=json.load(open(resourcefile,'r'))
        except:
            #the file is not existing; init class with default parameters
            self.res=dict()
            self.res['last_execution_time']=configStartCatalogueDate

        d=datetime.datetime.strptime(self.res['last_execution_time'],'%Y-%m-%dT%H:%M:%S')
        delta = datetime.timedelta(days=1)
        dayloop=0

        while d <= datetime.datetime.now():
            self.plan=list()
            
            print "*"*40
            print "Searching products ingested on day %s (%s/%s) " % (d.strftime("%Y-%m-%d"),dayloop,maxDayLoop)

            turl=url.replace('$YEAR',str(d.year)).replace('$MONTH', str(d.month)).replace('$DAY',str(d.day))
            prevskip=0
            skip=0
            total=0
            while(True):
                queryurl=turl.replace('$SKIP',str(skip))
                #print queryurl
                nProdPrevious=len(self.plan)
                self.getPlan_byurl(queryurl)
                nProdCurrent=len(self.plan)
                prevskip=skip
                skip+=nProdCurrent-nProdPrevious
                total+=nProdCurrent
                print "   found %s products (total %s)" % (nProdCurrent,total)
                self.storePlan()
                self.plan=list()
                #print "nProdCurrent %s; nProdPrevious %s; skip %s" % (nProdCurrent, nProdPrevious, skip)
                if prevskip==skip:
                    #no new record found; exiting from loop
                    #print "no new record found on this day"
                    break
        
            #set the execution time to be saved at the end of the loop in case the routine go till the end
            self.res['last_execution_time']=d.isoformat()
            #save the last execution time
            json.dump(self.res,open(resourcefile,'w'))

            time.sleep(3)
            
            d += delta
            dayloop+=1
            if dayloop>=maxDayLoop:
                print "maxDayLoop condition reached; exiting"
                break
        pass
    
    def getPlan_byurl(self,queryurl):
        queryurl=urllib.quote(queryurl,'/&?()$=')
        isOdata='odata' in queryurl
        if isOdata:
            print "Query URL ODATA: %s" %  queryurl
        else:
            print "Query URL OpenSearch: %s" %  queryurl
        self.conn.request('GET', queryurl, headers=self.headers)
        res = self.conn.getresponse()
        if res.status!=200:
            print "Failed connection (%s)" % res.reason
            try:
                data=res.read()
                import pprint
                pprint.pprint(res.__dict__)
                pprint.pprint(data.__dict__)
            except:
                pass
            return
        data=res.read()
        data=data.replace('&lt;','<')
        data=data.replace('&gt;','>')
        data=data.replace('<?xml version="1.0" encoding="UTF-8" standalone="no"?>','\n')
        open("dhus.xml", "w").write(data)
        parser = etree.fromstring(data)
        for prod in parser.findall(".//{*}entry"):
            note=dict()
            #id
            if isOdata:
                tmp=prod.find('.//{*}Id')
                note['id']=tmp.text
                #Product attributes
                tmp=prod.find('.//{*}file')
                fname=tmp.attrib['name']
                tmp=prod.find('.//{*}url')
                furl=tmp.text.replace('\n','').replace("'","\'")
            else:
                tmp=prod.find('.//{*}id')
                note['id']=tmp.text                
                #Product attributes
                tmp=prod.find('.//{*}title')
                fname=tmp.text+'.zip'
                tmp=prod.find('.//{*}link')
                furl=tmp.attrib['href']
            #tmp=prod.find('.//{*}coordinates')
            #pcoord=tmp.text

            #Creating libQueue object
            newItem=libQueue.newItem()
            newItem.setID(fname[:-4]+'.SAFE')
            newItem.addFile(fname,furl)
            newItem.setAgent(agent)
            newItem.setTarget(self.id)
            #note={'xml':etree.tostring(prod)}
            newItem.setNote(json.dumps(note))
            self.plan.append(newItem)
        return

    def getMetalink(self,queuedItem):
        #Not applicable for DHuS plugin as the getPlan already provide the url to be downloaded
        pass
    
    def getMetadata(self,queuedItem):
        if not os.path.exists(dhusMetadataRepository):
            try:
                os.makedirs(dhusMetadataRepository)
            except:
                print "ERROR: dhusMetadataRepository is not existing and cannot be created"
                print "       check config.ini setting"
                print "       directory: %s " % dhusMetadataRepository
                pass
        #query dhus for getting metadata
        produrl=urlmeta.replace('$ID',queuedItem.note['id'])
        self.conn.request('GET', produrl, headers=self.headers)
        res = self.conn.getresponse()
        if res.status!=200:
            print "Failed connection (%s)" % res.reason
            try:
                data=res.read()
                import pprint
                pprint.pprint(data.__dict__)
            except:
                pass
            return
        data=res.read()
        data=data.replace('&lt;','<')
        data=data.replace('<?xml version="1.0" encoding="UTF-8" standalone="no"?>','\n')

        targetFilename=getDhusMetadataFilename(queuedItem.id)
        targetFolder=os.path.split(targetFilename)[0]
        if not os.path.exists(targetFolder):
            os.makedirs(targetFolder)

        #try to parse data and reformat it
        try:
            #prettydata=etree.dump(etree.fromstring(data),pretty_print=True)
            xmldata=etree.fromstring(data)
            open(targetFilename, "w").write(etree.tostring(xmldata,pretty_print=True))
            #queuedItem.addFile(filename=queuedItem.id+metadatafile, url='',status=libQueue.cDwnStatusCompleted)
        except:
            open(targetFilename, "w").write(data)
            print "Failed to parse dhus metadata"
            traceback.print_exc(file=sys.stdout)
        return
    
    def parseMetadata(self,queuedItem):
        #parse manifest in local rep that has been already downloaded by getMetadta function
        self.openDhusMetadata(queuedItem)
        self.parseDhusMetadata(queuedItem)
        self.storeDhusMetadata(queuedItem)

    ## Search for the manifest and create file and xml handlers
    def openDhusMetadata(self,queuedItem):
        assert queuedItem.targettype=='dhus'
        queuedItem.metadataPath=getDhusMetadataFilename(queuedItem.id)
        queuedItem.metadataParser=etree.parse(queuedItem.metadataPath)
        return 

    ## Search for the manifest and create file and xml handlers
    def parseDhusMetadata(self,queuedItem):
        #if self.manifestParser:
        if hasattr(queuedItem,'metadataParser'):
            queuedItem.coordinatesKML=queuedItem.metadataParser.find('.//{*}coordinates').text
            #TODO: WARNING
            #DHUS footprint is wrong and coordinates are swapped
            #to take into account DHuS bug, the coordinates are swapped
            queuedItem.coordinatesWKT=libProduct.gml2wkt(queuedItem.coordinatesKML)
            queuedItem.coordinatesWKT=libProduct.gml2wkt_swap(queuedItem.coordinatesKML)
            for itag in ('Start','End'):
                val=queuedItem.metadataParser.find('.//{http://schemas.microsoft.com/ado/2007/08/dataservices}'+itag).text
                queuedItem.product.addJson({itag:val})
    
    def storeDhusMetadata(self,queuedItem):
        #qry="UPDATE product set size=%s, footprint=GeomFromText('%s') where id ='%s';" % (self.size, self.coordinatesWKT, self.id)
        qry="UPDATE product set footprint=GeomFromText('%s') where id ='%s';" % (queuedItem.coordinatesWKT, queuedItem.id)
        queuedItem.db.exe(qry)
        pass

def getDhusMetadataFilename(productid):
    #Evaluate partition and filename for dhus.xml
    try:
        part=re.search('\d{8}T\d{6}', productid).group()[2:8]
    except:
        part='000000'
    targetFilename='/%s/dhus_%s/%s' % (dhusMetadataRepository, part, productid+metadatafile)
    return targetFilename

def testworkflow():
    #check DB connection
    q=libQueue.queue()
    del q
    
    targets=dbif.getTargetList("type='dhus'")
    for itarget in targets:
        x=gmpPluginDhus(itarget)
        x.getPlan()
        #x.storePlan()
        del x

    #Process queue last time in a serial way
    #libQueue.serialWorkflow()
    
if __name__ == "__main__":
    #test()
    testworkflow()

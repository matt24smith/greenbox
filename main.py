#!/usr/bin/python3

"""
greenbox v0.2.0
matt smith
"""
from datetime import date as D
from datetime import datetime as DT
from datetime import timedelta
from matplotlib.font_manager import FontProperties]
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import os
import socketserver
import sqlite3
import sys
import threading
import time
import urllib.request
import requests


### CONFIG ###
PORT = 8000
SENSOR_UPDATE_INTERVAL = 60  # seconds
GRAPH_UPDATE_INTERVAL = 900  # 900s = 15m
sensor1ip = 'http://192.168.4.1:42000'
jsonfile = r"/var/www/html/projects/greenbox/greenbox.js"
graphfile = r"/var/www/html/projects/greenbox/graph.png"
palette = ['xkcd:sea blue', 'xkcd:leaf green', '#efa00b',
           '#d65108', '#591f0a', '#F7F7F2']


### some stuff ###
plt.ioff()
def timestamp(deltaHours=False): 
    if not deltaHours:
        return time.strftime("%Y-%m-%d %H:%M:%S") 
    else:
        newtime = DT.now() + timedelta(hours=i)
        return (newtime).strftime("%Y-%m-%d %H:%M:%S")


### Webserv ###
class Slave(threading.Thread):
    def run(self):
        self.kill = False
        self.ready = False
        import http.server
        Handler = http.server.SimpleHTTPRequestHandler
        try:
            httpd = socketserver.TCPServer(('0.0.0.0', PORT), Handler)
        except OSError as e:
            print (e)
            print("%s\tCaught socket exception, retrying..." % timestamp())
            time.sleep(10)
            self.run()

        self.ready = True

        while not self.kill:  # work hard until seppuku 
            httpd.handle_request()

        return

def json2js(sensor1):
    jsonString = "jsonData = JSON.stringify(["
    jsonString += str(sensor1)
    jsonString += "]);"

    return jsonString

### Sensor related functions ###
def read_sensor():
    try:
        req = requests.get(sensor1ip)
    except Exception as e:
        print(e)
        print("%s\tAn unknown error occurred, retrying..." % timestamp())
        time.sleep(10)
        return False

    if req.status_code is 200:
        jdata = req.json()
        print("%s\t%s" % (timestamp(), jdata))
        return jdata
    else:
        print("%s\tUnknown status code %d, retrying..."
              % (timestamp(), req.status_code))
        time.sleep(10)
        return False


def dbinsert(jdata, c):
    if not (np.isnan(jdata["celsius"]) 
            or np.isnan(jdata["humidity"]) 
            or jdata["reservoir"] > 40 
            or jdata["ec"] <= 0 ):
        c.execute("INSERT INTO sensor1 VALUES " + 
                  ("('%s', %s, %s, %s, %s, %s, %s)" 
                  % (jdata['time'], jdata["celsius"], jdata["humidity"], 
                     jdata["heat index"], jdata["ph"], jdata["ec"], 
                     jdata["reservoir"])))
        return True

    else:
        print("%s\tReceived garbage data from sensor" % timestamp())
        return False


def graph(c, debug=False):
    """
    [(0, 'time', 'datetime', 0, None, 0),
     (1, 'temp', 'float', 0, None, 0),
     (2, 'humidity', 'float', 0, None, 0),
     (3, 'heatindex', 'float', 0, None, 0),
     (4, 'ph', 'float', 0, None, 0),
     (5, 'ec', 'float', 0, None, 0),
     (6, 'reservoir', 'float', 0, None, 0)]
    """

    font = FontProperties()
    font.set_family('monospace')
    
    query = (r"SELECT * FROM sensor1 WHERE time BETWEEN "
             + r"datetime('now', 'localtime', '-1 days') AND "
             + r"datetime('now', 'localtime')")
    c.execute(query)
    res = np.array(c.fetchall())

    if len(res) < 10:
        print("%s\tNot enough recent data to make graph" % timestamp())
        return

    fig, axs = plt.subplots(4, 1, sharex=True, figsize=(8, 6))
    #fig.patch.set_facecolor(palette[5])
    plt.suptitle("Sensor Data (24h)", fontproperties=font)
    plt.subplots_adjust(hspace=0.5, top=0.85, bottom=0.1)
    dates = [DT.strptime(t, "%Y-%m-%d %H:%M:%S") for t in res[:,0]]
    hours = mdates.HourLocator(interval=2)
    mins = mdates.MinuteLocator(byminute=[0, 30])
    fmt = mdates.DateFormatter("%H:%M")
    
    axs[0].set_title("Temperature (*C)", fontproperties=font)
    axs[0].plot(dates, res[:, 1].astype(float), c=palette[3], label="Ambient")
    axs[0].plot(dates, res[:, 6].astype(float), c=palette[0], label="Reservoir")
    axs[0].legend()
    axs[1].set_title("Humidity (%)", fontproperties=font)
    axs[1].plot(dates, res[:, 2].astype(float), c=palette[0])
    axs[2].set_title("Power of Hydrogen (pH)", fontproperties=font)
    axs[2].plot(dates, res[:, 4].astype(float), c=palette[1])    
    axs[3].set_title("Conductivity (mS/cm)", fontproperties=font)
    axs[3].plot(dates, (res[:, 5].astype(float)), c=palette[2])
    
    for ax in axs:
        ax.grid()
        ax.xaxis.set_major_locator(hours)
        ax.xaxis.set_major_formatter(fmt)
        ax.xaxis.set_minor_locator(mins)
        ax.set_facecolor(palette[5])

    today = D.strftime(D.today(), "%m-%d")
    if debug:
        plt.xlabel("Time (%s debug=True)" % timestamp(), fontproperties=font)
    else:
        plt.xlabel("Time (%s)" % today, fontproperties=font)
    fig.autofmt_xdate()
    #plt.show()
    #os.rename(graphfile, (graphfile[:-4]+".old.png"))
    plt.savefig(graphfile, facecolor=palette[5], edgecolor="red")
    plt.close()
    
    writeJS(jsonfile)

    return


def writeJS(jsonfile):
    #jsfile = r"/var/www/html/projects/greenbox/greenbox.js"
    
    filetext = "var imgtag = \"<img src='graph.png?"
    filetext += str(int(time.time()))
    filetext += "' alt='Sensor Data (24h)'></img>\"\n"
    filetext += "document.getElementById('graphImg').innerHTML=imgtag\n"
    
    with open (jsonfile, "w") as f:
        f.write(filetext)


### main loop ###
def update(c, conn, webslave=None):

#    while(webslave.ready is False):
#        print("%s\tWaiting for webslave..." % timestamp())
#        time.sleep(10)
    
    loopcounter = 0
    sensor_sleeptime = 0
    graph_sleeptime = 0

    while (True):
        jdata = read_sensor()
        if jdata is False: continue
            
        with open(indexfile, 'w') as f:
            f.write(json2js(jdata))

        dbinsert(jdata, c)
    
        loopcounter += 1

        if sensor_sleeptime == graph_sleeptime:
            conn.commit()
            graph(c)

        t = time.time()
        sensor_sleeptime = SENSOR_UPDATE_INTERVAL - ((t % SENSOR_UPDATE_INTERVAL))
        graph_sleeptime = GRAPH_UPDATE_INTERVAL - ((t % GRAPH_UPDATE_INTERVAL))
        time.sleep(sensor_sleeptime)
        
        #questionable 
        if sensor_sleeptime - .75 > 0: time.sleep(sensor_sleeptime - .75)



if __name__ == '__main__':
#    webslave = Slave()
#    webslave.start()

    conn = sqlite3.connect("./sensordata.db")
    c = conn.cursor()

    try:
        update(c, conn)
    except KeyboardInterrupt as e:
        print("\n%s\tCTRL-C Detected. Closing threads..." % timestamp())
#        webslave.kill = True
        conn.commit()
        c.close()
        conn.close()
#        urllib.request.urlopen('http://127.0.0.1:8000') # slave's final request
#        requests.get('http://127.0.0.1:8000')
#        webslave.join()
    except Exception as e:
        print(e)
        print("\n%s\tSomething bad happened, attempting to shutdown gracefully" 
              % timestamp())
#        webslave.kill = True
        conn.commit()
        c.close()
        conn.close()
#        urllib.request.urlopen('http://127.0.0.1:8000') # slave's final request
#        requests.get('http://127.0.0.1:8000')
#        webslave.join()

    sys.exit()

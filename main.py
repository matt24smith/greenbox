#!/usr/bin/env python3

"""
greenbox v0.2.0
matt smith
"""
from datetime import date as D
from datetime import datetime as DT
from datetime import timedelta
from matplotlib.font_manager import FontProperties
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.ioff()
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
phpfile = r"/var/www/html/projects/greenbox/graph.php"
graphfile = r"/var/www/html/projects/greenbox/graph.png"
palette = ['xkcd:sea blue', 'xkcd:leaf green', '#efa00b',
           '#d65108', '#591f0a', '#F7F7F7']


def timestamp(deltaHours=False): 
    if not deltaHours:
        return time.strftime("%Y-%m-%d %H:%M:%S") 
    else:
        newtime = DT.now() + timedelta(hours=deltaHours)
        return (newtime).strftime("%Y-%m-%d %H:%M:%S")


class Slave(threading.Thread):
    ### Webserv ###
    def run(self):
        self.kill = False
        self.ready = False
        import http.server
        handler = http.server.SimpleHTTPRequestHandler
        try:
            httpd = socketserver.TCPServer(('0.0.0.0', PORT), handler)
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
    jsonString = "\njsonData = JSON.stringify(["
    jsonString += str(sensor1)
    jsonString += "]);\n"

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


def graph(c, debug=False, daterange=False):
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
    black = (0.0471,0.0701,0.0471)  # rgb
    
    if daterange is False:
        query = (r"SELECT * FROM sensor1 WHERE time BETWEEN "
                 + r"datetime('now', 'localtime', '-1 days') AND "
                 + r"datetime('now', 'localtime')")
    else:
        query = (r"SELECT * FROM sensor1 WHERE time BETWEEN "
                 + r"datetime('now', 'localtime', '" + str(daterange[0]) 
                 +" days') AND "
                 + r"datetime('now', 'localtime', '" + str(daterange[1])
                 + " days')")

    c.execute(query)
    res = np.array(c.fetchall())

    if len(res) < 10:
        print("%s\tNot enough recent data to make graph" % timestamp())
        return

    fig, axs = plt.subplots(4, 1, sharex=True, figsize=(8, 6))
    plt.suptitle("Sensor Data (24h)", y=1, fontproperties=font, fontsize=16, color=black)
    plt.subplots_adjust(hspace=0.5, top=0.85, bottom=0.1)
    dates = [DT.strptime(t, "%Y-%m-%d %H:%M:%S") for t in res[:,0]]
    hours = mdates.HourLocator(interval=2)
    mins = mdates.MinuteLocator(byminute=[0, 30])
    fmt = mdates.DateFormatter("%H:%M")
    
    axs[0].set_title("Temperature (*C)", fontproperties=font, color=black)
    axs[0].plot(dates, res[:, 1].astype(float), c=palette[3], label="Ambient", zorder=5)
    axs[0].fill_between(dates, res[:, 1].astype(float), alpha=0.5, color=palette[5], zorder=3)
    axs[0].fill_between(dates, res[:, 1].astype(float), alpha=0.2, color=palette[3], zorder=4)
    axs[0].plot(dates, res[:, 6].astype(float), c=palette[0], label="Reservoir", zorder=2)
    axs[0].fill_between(dates, res[:, 6].astype(float), alpha=0.27, color=palette[0], zorder=1)
    l = axs[0].legend()
    for text in l.get_texts():
        text.set_color("#0C120C")
    axs[0].set_ylim(20, 27.5)
    axs[1].set_title("Humidity (%)", fontproperties=font, color=black)
    axs[1].plot(dates, res[:, 2].astype(float), c=palette[0])
    axs[1].fill_between(dates, res[:, 2].astype(float), alpha=0.27, color=palette[0])
    axs[1].set_ylim(15, 80)
    axs[2].set_title("Power of Hydrogen (pH)", fontproperties=font, color=black)
    axs[2].plot(dates, res[:, 4].astype(float), c=palette[1])
    axs[2].fill_between(dates, res[:, 4].astype(float), alpha=0.24, color=palette[1])
    axs[2].set_ylim(4,8)
    axs[3].set_title("Conductivity (mS/cm)", fontproperties=font, color=black)
    axs[3].plot(dates, (res[:, 5].astype(float)), c=palette[2])
    axs[3].fill_between(dates, res[:, 5].astype(float), alpha=0.2, color=palette[2])
    axs[3].set_ylim(0, 2.25)
    
    for ax in axs:
        ax.grid()
        ax.xaxis.set_major_locator(hours)
        ax.xaxis.set_major_formatter(fmt)
        ax.xaxis.set_minor_locator(mins)
        ax.set_facecolor(palette[5])
        ax.tick_params(color=black, labelcolor=black)
        for spine in ax.spines.values():
            spine.set_edgecolor(black)

    today = D.strftime(D.today(), "%b %d, %Y")
    if debug:
        plt.xlabel("Time (%s debug=True)" % 
                   timestamp(), fontproperties=font, labelpad=20, color=black)
    else:
        plt.xlabel("Time (%s)" % 
                   today, fontproperties=font, labelpad=20, color=black)
    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    if debug:
        plt.show()
    else:
        print(timestamp() + " Saving fig to " + graphfile)
        plt.savefig(graphfile, facecolor=palette[5], edgecolor="red", dpi=150)
        plt.close()
        writeJS(res, jsonfile)
    
    return


def writeJS(res, jsonfile):
#    filetext = "var imgtag = \"<img src='projects/greenbox/graph.png?"
#    filetext += str(int(time.time()))
#    filetext += "' alt='Sensor Data (24h)'></img>\"\n"
#    filetext += "document.getElementById('graphImg').innerHTML = imgtag\n"
    
    jsonStream = {x[0] : list(x[1:]) for x in res}
    filetext = json2js(jsonStream)
    
    with open (jsonfile, "w") as f:
        f.write(filetext)
        
        
def writePHP(phpfile):
    filetext = "<!-- graph.png -->\n"
    filetext += "<img src='projects/greenbox/graph.png?"
    filetext += str(int(time.time()))
    filetext += "' alt='Sensor Data (24h)'>\n"
    filetext += "<!-- /graph.png -->\n"
    
    with open(phpfile, "w") as f:
        f.write(filetext)


### main loop ###
def update(c, conn, webslave=False):
    sensor_sleeptime = 0
    graph_sleeptime = 0
    
#    while(webslave.ready is False):
#        print("%s\tWaiting for webslave..." % timestamp())
#        time.sleep(10)

    while (True):
#        jdata = read_sensor()
#        if jdata is False: continue

#        if not (np.isnan(jdata["celsius"]) or np.isnan(jdata["humidity"])):
#            c.execute("INSERT INTO sensor1 VALUES ('%s', %s, %s)"
#                      % (timestamp(), jdata["celsius"], jdata["humidity"]))
#        else:
#            print("%s\tReceived garbage data from sensor" % timestamp())

        if sensor_sleeptime == graph_sleeptime:
            conn.commit()
            graph(c, daterange=[-320, -319])
            writePHP(phpfile)

        t = time.time()
        sensor_sleeptime = SENSOR_UPDATE_INTERVAL - ((t % SENSOR_UPDATE_INTERVAL))
        graph_sleeptime = GRAPH_UPDATE_INTERVAL - ((t % GRAPH_UPDATE_INTERVAL))
        time.sleep(sensor_sleeptime)



if __name__ == '__main__':
#    webslave = Slave()
#    webslave.start()

    conn = sqlite3.connect("./sensordata.db")
    c = conn.cursor()

    try:
        print("Serving up some sweet sweet data...")
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

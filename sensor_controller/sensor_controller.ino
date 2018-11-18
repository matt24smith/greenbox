#include <DallasTemperature.h>
#include <OneWire.h>

#include <Adafruit_Sensor.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <DHT_U.h>
#include <ESP8266WiFi.h>
#include <EEPROM.h>
#include <FS.h>

#define StartConvert 0
#define ReadTemperature 1

/*      PINS      */

const int selectPins[3] = {4, 5, 16}; // S0, S1, S2
const int zIn = A0; // Connect common (Z) to 0 (PWM-capable)
const int DS18B20Pin = 0;
const int dhtPin = 1;

const int phMuxpin = 5;
const int ecMuxpin = 1;
//const int potMuxpin = 2;
//const int ledMuxpin = 7;

/*      CONFIG    */

#define port 42000
#define ap "greenbox"
#define secret "newpassword"

/* 
formula for ph offset and coefficient:
  x1 = 4.0 actual value sample 1
  x2 = 6.86 actual value sample 2
  y1 = observed voltage sample 1
  y2 = observed voltage sample 2

  x1 = y1(x) + b
  x2 = y2(x) + b 

  x = coefficient
  b = offset
*/

#define ECOFFSET      -0.04
#define ECCOEFFICIENT 1.021
#define PHOFFSET      -7.006        // its dead :/
#define PHCOEFFICIENT 1.30135



IPAddress ip(192, 168, 4, 20);
IPAddress dns(8, 8, 8, 8);
IPAddress gateway(192, 168, 4, 200);
IPAddress subnet(255, 255, 255, 0);

/*      INIT      */

WiFiServer server(port);
StaticJsonBuffer<200> jsonBuffer;
JsonObject& jdata = jsonBuffer.createObject();
DHT dht(dhtPin, DHT22);
OneWire ds(DS18B20Pin);

void selectMuxPin(byte pin) {
  if (pin > 7) return;
  for (int i = 0; i < 3; i++)
  {
    if (pin & (1 << i))
      digitalWrite(selectPins[i], HIGH);
    else
      digitalWrite(selectPins[i], LOW);
  }
}

/* Commented out for now while output is disabled on mux */

//void blinkled(int y) {
//  //  pinMode(zOut, OUTPUT);
//  int LED_ON_TIME = 500;           // 0.5s
//  int DELAY_TIME = ((float)LED_ON_TIME / 512.0) * 1000;
//  selectMuxPin(y);
//  for (int intensity = 0; intensity <= 255; intensity++)
//  {
//    analogWrite(zOut, intensity);
//    delayMicroseconds(DELAY_TIME);
//  }
//  for (int intensity = 255; intensity >= 0; intensity--)
//  {
//    analogWrite(zOut, intensity);
//    delayMicroseconds(DELAY_TIME);
//  }
//}

float get_temp() {
  return dht.readTemperature();
}

float get_humidity() {
  return dht.readHumidity();
}

float get_restemp() {
  float temperature = TempProcess(ReadTemperature);
  TempProcess(StartConvert);

  return temperature;
}

//float get_potentiometer() {
//  selectMuxPin(potMuxpin);
//  float sensorValue = analogRead(zIn);
//
//  return sensorValue;
//}


float get_ph() {
  
  selectMuxPin(phMuxpin);
  
  float analogTotal = 0;

  for (int ix = 0; ix < 25; ix++) {
    analogRead(zIn);
    delay(3);
  }

  for ( int ix = 0; ix < 10; ix++) {
    analogTotal += analogRead(zIn);
    delay(10);
  }
//
//  float PHOFFSET = 0;
//
//  if ((analogTotal / 10) > 900) {
//    return 0;
//  }
//  else if ((analogTotal / 10) > 700) {
//    PHOFFSET = -393.7;// false
//  }
//  else if ((analogTotal / 10) > 640) {
//   PHOFFSET = -498.2;
//  }
//  else if ((analogTotal / 10) > 580) {
//    PHOFFSET = -482.94;
//  }
//  else if ((analogTotal / 10) > 460) {
//    PHOFFSET = -391.95;
//  }
//  else {
//    return 14;
//  }

  
  float ph = PHCOEFFICIENT * ( 3.5 * (analogTotal / 10) * 5.0 / 1024.0) + PHOFFSET;

  return ph;
}

float get_ph_raw(){
  selectMuxPin(phMuxpin);
  float analogTotal = 0;

  for (int ix = 0; ix < 50; ix++) {
    analogRead(zIn);
    delay(1);
  }

  for ( int ix = 0; ix < 10; ix++) {
    analogTotal += analogRead(zIn);
    delay(10);
  }

  return (analogTotal / 10) / 1024.0;
}

float get_ec() {
  unsigned long AnalogValueTotal = 0;
  unsigned int AnalogAverage = 0, averageVoltage = 0;
  float temperature, EC;

  selectMuxPin(ecMuxpin);

  int i = 0;

  for (i = 0; i < 10; i++) {
    AnalogValueTotal += analogRead(zIn);
    delay(10);
  }

  AnalogAverage = AnalogValueTotal / 10;
  averageVoltage = AnalogAverage * (float) 5000 / 1024;

  temperature = get_restemp();

  float tempCoefficient = 1.0 + 0.0185 * (temperature - 25.0);
  float voltageCoefficient = (float)averageVoltage / tempCoefficient;

  EC = 5 * ECCOEFFICIENT * voltageCoefficient / 1000 + ECOFFSET;

//  //  if (voltageCoefficient < 150) {
//  if (EC < 0.5) {
//    // no solution
//    return (-1);
//  }
//  //  else if (voltageCoefficient > 3300) {
//  else 
  if (EC > 17) {
    // out of range
    return (-2);
  }
  else {

    return EC;
  }
}

float TempProcess(bool ch)
{
  //returns the temperature from one DS18B20 in DEG Celsius
  static byte data[12];
  static byte addr[8];
  static float TemperatureSum;
  if (!ch) {
    if ( !ds.search(addr)) {
      Serial.println("no more sensors on chain, reset search!");
      ds.reset_search();
      return 0;
    }
    if ( OneWire::crc8( addr, 7) != addr[7]) {
      Serial.println("CRC is not valid!");
      return 0;
    }
    if ( addr[0] != 0x10 && addr[0] != 0x28) {
      Serial.print("Device is not recognized!");
      return 0;
    }
    ds.reset();
    ds.select(addr);
    ds.write(0x44, 1); // start conversion, with parasite power on at the end
  }
  else {
    byte present = ds.reset();
    ds.select(addr);
    ds.write(0xBE); // Read Scratchpad
    for (int i = 0; i < 9; i++) { // we need 9 bytes
      data[i] = ds.read();
    }
    ds.reset_search();
    byte MSB = data[1];
    byte LSB = data[0];
    float tempRead = ((MSB << 8) | LSB); //using two's compliment
    TemperatureSum = tempRead / 16;
  }
  return TemperatureSum;
}

void handle_request(WiFiClient client) {
  boolean blank_line = true;
  while (client.connected()) {
    if (client.available()) {
      char c = client.read();
      if (c == '\n' && blank_line) {
        selectMuxPin(0);

        jdata["celsius"] = get_temp();
        jdata["humidity"] = get_humidity();
        jdata["heat index"] = dht.computeHeatIndex(jdata["celsius"], jdata["humidity"], false);
        jdata["ph"] = get_ph();
        jdata["ec"] = get_ec();
        jdata["reservoir"] = get_restemp();
        jdata["ph raw voltage"] = get_ph_raw();
        //        jdata["potentiometer"] = get_potentiometer();


        client.println("HTTP/1.1 200 OK");
        client.println("Content-Type: text/html");
        client.println("Connection: close\n");
        jdata.printTo(client);
        client.println();
        break;
      }
      if (c == '\n') {
        // when starts reading a new line
        blank_line = true;
      }
      else if (c != '\r') {
        // when finds a character on the current line
        blank_line = false;
      }
    }
  }
  client.stop();
  blink(50);
  blink(50);
  blink(50);
  blink(50);
}

/*      MAIN PROGRAM      */

void setup() {
  Serial.begin(115200);
  pinMode(BUILTIN_LED, OUTPUT); // blinker
  pinMode(zIn, INPUT);
  pinMode(selectPins[0], OUTPUT);
  pinMode(selectPins[1], OUTPUT);
  pinMode(selectPins[2], OUTPUT);

  WiFi.mode(WIFI_AP);
  Serial.print("\nSetting soft-AP configuration ... ");
  Serial.println(WiFi.softAPConfig(ip, gateway, subnet) ? "Ready" : "Failed!");
  Serial.print("Setting soft-AP ... ");
  Serial.println(WiFi.softAP(ap, secret) ? "Ready" : "Failed!");
  Serial.print("Soft-AP IP address = ");
  Serial.println(WiFi.softAPIP());
  server.begin();
  blink(50);
  WiFi.begin();
  blink(50);
  dht.begin();
  blink(50);
  TempProcess(StartConvert);   //let the DS18B20 start the convert
  blink(50);

}

void loop() {
  WiFiClient client = server.available();
  if (client) {
    handle_request(client);
  }

  delay(300);
}

/*      HELPER FUNCTIONS    */

void blink(int delaytime) {
  digitalWrite(BUILTIN_LED, LOW);  // actually is high
  delay(delaytime);
  digitalWrite(BUILTIN_LED, HIGH);  // actually is low
  delay(delaytime);
}

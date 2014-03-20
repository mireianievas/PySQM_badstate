#!/usr/bin/env python

'''
PySQM plotting program
____________________________

Copyright (c) Miguel Nievas <miguelnievas[at]ucm[dot]es>

This file is part of PySQM.

PySQM is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

PySQM is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with PySQM.  If not, see <http://www.gnu.org/licenses/>.

____________________________

Requirements:
 - Python 2.7
 - Pyephem
 - Numpy
 - Socket (for SQM-LE). It should be part of standard python install.
 - Serial (for SQM-LU)
 - python-mysql to enable DB datalogging [optional].

____________________________
'''

__author__ = "Miguel Nievas"
__copyright__ = "Copyright (c) 2014 Miguel Nievas"
__credits__ = [\
 "Miguel Nievas @ UCM",\
 "Jaime Zamorano @ UCM",\
 "Laura Barbas @ OAN",\
 "Pablo de Vicente @ OAN"\
 ]
__license__ = "GNU GPL v3"
__shortname__ = "PySQM"
__longname__ = "Python Sky Quality Meter pipeline"
__version__ = "2.4"
__maintainer__ = "Miguel Nievas"
__email__ = "miguelnr89[at]gmail[dot]com"
__status__ = "Development" # "Prototype", "Development", or "Production"



import os, sys
import signal
import numpy as np
import matplotlib
import matplotlib.ticker as ticker
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import scale as mscale
from matplotlib import transforms as mtransforms
import ephem
from datetime import datetime,date,timedelta

import pysqm_config
Options = pysqm_config.__dict__
Keys = Options.keys()
Values = Options.values()
Items = Options.items()

# Import config variables
for index in xrange(len(Items)):
	if "__" not in str(Items[index][0]):
		exec("from pysqm_config import "+str(Items[index][0]))

from pysqm_common import *

for directory in [monthly_data_directory,daily_graph_directory,current_graph_directory]:
	if not os.path.exists(directory):
		os.makedirs(directory)


class Ephemerids():
	def __init__(self):
		self.Observatory = define_ephem_observatory()

	def ephem_date_to_datetime(self,ephem_date):
		# Convert ephem dates to datetime
		date_,time_ = str(ephem_date).split(' ')
		date_ = date_.split('/')
		time_ = time_.split(':')

		return(datetime.datetime(\
			int(date_[0]),int(date_[1]),int(date_[2]),\
			int(time_[0]),int(time_[1]),int(time_[2])))

	def end_of_the_day(self,thedate):
		newdate = thedate+datetime.timedelta(days=1)
		newdatetime = datetime.datetime(\
			newdate.year,\
			newdate.month,\
			newdate.day,0,0,0)
		newdatetime = newdatetime-datetime.timedelta(hours=_local_timezone)

		return(newdatetime)


	def calculate_moon_ephems(self,thedate):
		# Moon ephemerids
		self.Observatory.horizon = '0'
		self.Observatory.date = str(self.end_of_the_day(thedate))

		# Moon phase
		Moon = ephem.Moon()
		Moon.compute(self.Observatory)
		self.moon_phase = Moon.phase
		self.moon_maxelev = Moon.transit_alt

		try:
			float(self.moon_maxelev)
		except:
			# The moon has no culmination time for 1 day
			# per month, so there is no max altitude.
			# As a workaround, we use the previous day culmination.
			# The error should be small.

			# Set the previous day date
			thedate2 = thedate - datetime.timedelta(days=1)
			self.Observatory.date = str(self.end_of_the_day(thedate2))
			Moon2 = ephem.Moon()
			Moon2.compute(self.Observatory)
			self.moon_maxelev = Moon2.transit_alt

			# Recover the real date
			self.Observatory.date = str(self.end_of_the_day(thedate))

		# Moon rise and set
		self.moon_prev_rise = \
		 self.ephem_date_to_datetime(self.Observatory.previous_rising(ephem.Moon()))
		self.moon_prev_set  = \
		 self.ephem_date_to_datetime(self.Observatory.previous_setting(ephem.Moon()))
		self.moon_next_rise = \
		 self.ephem_date_to_datetime(self.Observatory.next_rising(ephem.Moon()))
		self.moon_next_set  = \
		 self.ephem_date_to_datetime(self.Observatory.next_setting(ephem.Moon()))

	def calculate_twilight(self,thedate,twilight=-18):
		'''
		Changing the horizon forces ephem to
		calculate different types of twilights:
		-6: civil,
		-12: nautical,
		-18: astronomical,
		'''
		self.Observatory.horizon = str(twilight)
		self.Observatory.date = str(self.end_of_the_day(thedate))

		self.twilight_prev_rise = self.ephem_date_to_datetime(\
		 self.Observatory.previous_rising(ephem.Sun(),use_center=True))
		self.twilight_prev_set = self.ephem_date_to_datetime(\
		 self.Observatory.previous_setting(ephem.Sun(),use_center=True))
		self.twilight_next_rise = self.ephem_date_to_datetime(\
		 self.Observatory.next_rising(ephem.Sun(),use_center=True))
		self.twilight_next_set = self.ephem_date_to_datetime(\
		 self.Observatory.next_setting(ephem.Sun(),use_center=True))



class SQMData():
	# Split pre and after-midnight data

	class premidnight:
		pass

	class aftermidnight:
		pass

	class Statistics:
		pass

	def __init__(self,filename,Ephem):
		self.all_night_sb = []
		self.all_night_dt = []
		self.all_night_temp = []

		for variable in [\
		 'utcdates','localdates','sun_altitudes',\
		 'temperatures','tick_counts','frequencies',\
		 'night_sbs','label_dates','sun_altitude']:
			setattr(self.premidnight,variable,[])
			setattr(self.aftermidnight,variable,[])

		self.load_rawdata(filename)
		self.process_rawdata(Ephem)
		self.check_number_of_nights()

	def extract_metadata(self,raw_data_and_metadata):
		metadata_lines = [\
		 line for line in raw_data_and_metadata \
		 if format_value(line)[0]=='#']

		# Extract the serial number
		serial_number_line = [\
		 line for line in metadata_lines \
		 if 'SQM serial number:' in line][0]
		self.serial_number = format_value(serial_number_line.split(':')[-1])

	def check_validdata(self,data_line):
		try:
			assert(format_value(data_line)[0]!='#')
			assert(format_value(data_line)[0]!='')
		except:
			return(False)
		else:
			return(True)

	def load_rawdata(self,filename):
		'''
		Open the file, read the data and close the file
		'''
		sqm_file = open(filename, 'r')
		raw_data_and_metadata = sqm_file.readlines()
		self.metadata = self.extract_metadata(raw_data_and_metadata)

		self.raw_data = [\
		 line for line in raw_data_and_metadata \
		 if self.check_validdata(line)==True]
		sqm_file.close()

	def process_datetimes(self,str_datetime):
		'''
		Get date and time in a str format
		Return as datetime object
		'''
		str_date,str_time = str_datetime.split('T')

		year  = int(str_date.split('-')[0])
		month = int(str_date.split('-')[1])
		day   = int(str_date.split('-')[2])

		# Time may be not complete. Workaround
		hour   = int(str_time.split(':')[0])
		try:
			minute = int(str_time.split(':')[1])
		except:
			minute = 0
			second = 0
		else:
			try:
				second = int(str_time.split(':')[2])
			except:
				second = 0

		return(datetime.datetime(year,month,day,hour,minute,second))

	def process_rawdata(self,Ephem):
		'''
		Get the important information from the raw_data
		and put it in a more useful format
		'''
		self.raw_data = format_value_list(self.raw_data)

		for k,line in enumerate(self.raw_data):
			# DateTime extraction
			utcdatetime = self.process_datetimes(line[0])
			localdatetime = self.process_datetimes(line[1])

			# Check that datetimes are corrent
			calc_localdatetime = utcdatetime+timedelta(hours=_local_timezone)
			assert(calc_localdatetime == localdatetime)

			# Set the datetime for astronomical calculations.
			Ephem.Observatory.date = ephem.date(utcdatetime)

			# Date in str format: 20130115
			label_date = str(localdatetime.date()).replace('-','')

			# Temperature
			temperature = float(line[2])
			# Counts
			tick_counts = float(line[3])
			# Frequency
			frequency   = float(line[4])
			# Night sky background
			night_sb    = float(line[5])
			# Define sun in pyephem
			Sun = ephem.Sun(Ephem.Observatory)

			self.premidnight.label_date=[]
			self.aftermidnight.label_dates=[]


			if localdatetime.hour > 12:
				self.premidnight.utcdates.append(utcdatetime)
				self.premidnight.localdates.append(localdatetime)
				self.premidnight.temperatures.append(temperature)
				self.premidnight.tick_counts.append(tick_counts)
				self.premidnight.frequencies.append(frequency)
				self.premidnight.night_sbs.append(night_sb)
				self.premidnight.sun_altitude.append(Sun.alt)
				if label_date not in self.premidnight.label_dates:
					self.premidnight.label_dates.append(label_date)
			else:
				self.aftermidnight.utcdates.append(utcdatetime)
				self.aftermidnight.localdates.append(localdatetime)
				self.aftermidnight.temperatures.append(temperature)
				self.aftermidnight.tick_counts.append(tick_counts)
				self.aftermidnight.frequencies.append(frequency)
				self.aftermidnight.night_sbs.append(night_sb)
				self.aftermidnight.sun_altitude.append(Sun.alt)
				if label_date not in self.aftermidnight.label_dates:
					self.aftermidnight.label_dates.append(label_date)

			# Data for the complete night
			self.all_night_dt.append(utcdatetime) # Must be in UTC!
			self.all_night_sb.append(night_sb)
			self.all_night_temp.append(temperature)


	def check_number_of_nights(self):
		'''
		Check that the number of nights is exactly 1 and
		extract it to a new variable self.Night.
		Needed for the statistics part of the analysis and
		to make the plot.
		'''

		if np.size(self.premidnight.localdates)>0:
			self.Night = np.unique([DT.date() \
			 for DT in self.premidnight.localdates])[0]
		elif np.size(self.aftermidnight.localdates)>0:
			self.Night = np.unique([(DT-datetime.timedelta(hours=12)).date() \
			 for DT in self.aftermidnight.localdates])[0]
		else:
			print('Warning, No Night detected.')
			self.Night = None

	def data_statistics(self,Ephem):
		'''
		Make statistics on the data.
		Useful to summarize night conditions.
		'''
		def select_bests(values,number):
			return(np.sort(values)[::-1][0:number])

		def fourier_filter(array,nterms):
			'''
			Make a fourier filter for the first nterms terms.
			'''
			array_fft = np.fft.fft(array)
			# Filter data
			array_fft[nterms:]=0
			filtered_array = np.fft.ifft(array_fft)
			return(filtered_array)

		astronomical_night_filter = (\
		 (np.array(self.all_night_dt)>Ephem.twilight_prev_set)*\
		 (np.array(self.all_night_dt)<Ephem.twilight_next_rise))

		if np.sum(astronomical_night_filter)>10:
			self.astronomical_night_sb = \
		 		np.array(self.all_night_sb)[astronomical_night_filter]
			self.astronomical_night_temp = \
		 		np.array(self.all_night_temp)[astronomical_night_filter]
		else:
			print(\
			 'Warning, < 10 points in astronomical night, '+\
			 ' using the whole night data instead')
			self.astronomical_night_sb = self.all_night_sb
			self.astronomical_night_temp = self.all_night_temp

		Stat = self.Statistics
		#with self.Statistics as Stat:
		# Complete list
		Stat.mean   = np.mean(self.astronomical_night_sb)
		Stat.median = np.median(self.astronomical_night_sb)
		Stat.std    = np.median(self.astronomical_night_sb)
		Stat.number = np.size(self.astronomical_night_sb)
		# Only the best 1/100th.
		Stat.bests_number = int(1+Stat.number/50.)
		Stat.bests_mean   = np.mean(select_bests(self.astronomical_night_sb,Stat.bests_number))
		Stat.bests_median = np.median(select_bests(self.astronomical_night_sb,Stat.bests_number))
		Stat.bests_std    = np.std(select_bests(self.astronomical_night_sb,Stat.bests_number))
		Stat.bests_err    = Stat.bests_std*1./np.sqrt(Stat.bests_number)

		Stat.model_nterm = Stat.bests_number
		data_smooth = fourier_filter(self.astronomical_night_sb,nterms=Stat.model_nterm)
		data_residuals = self.astronomical_night_sb-data_smooth
		Stat.data_model_abs_meandiff = np.mean(np.abs(data_residuals))

		# Other interesting data
		Stat.min_temperature = np.min(self.astronomical_night_temp)
		Stat.max_temperature = np.max(self.astronomical_night_temp)


class Plot():
	def __init__(self,Data,Ephem):
		plt.hold(True)
		self.make_figure(figsize=(8,8),thegraph_altsun=True,thegraph_time=True)
		self.plot_data(Data,Ephem)
		self.plot_moonphase(Ephem)
		self.plot_twilight(Ephem)
		plt.hold(False)

	def plot_moonphase(self,Ephem):
		if Ephem.moon_next_rise > Ephem.moon_next_set:
			# We need to divide the plotting in two phases
			#(pre-midnight and after-midnight)
			self.thegraph_time.axvspan(\
			 Ephem.moon_prev_rise+datetime.timedelta(hours=_local_timezone),\
			 Ephem.moon_next_set+datetime.timedelta(hours=_local_timezone),\
		 	 edgecolor='r',facecolor='r', alpha=0.1,clip_on=True)
		else:
			self.thegraph_time.axvspan(\
			 Ephem.moon_prev_rise+datetime.timedelta(hours=_local_timezone),\
			 Ephem.moon_prev_set+datetime.timedelta(hours=_local_timezone),\
			 edgecolor='r',facecolor='r', alpha=0.1,clip_on=True)
			self.thegraph_time.axvspan(\
			 Ephem.moon_next_rise+datetime.timedelta(hours=_local_timezone),\
			 Ephem.moon_next_set+datetime.timedelta(hours=_local_timezone),\
			 edgecolor='r',facecolor='r', alpha=0.1,clip_on=True)

	def plot_twilight(self,Ephem):
		self.thegraph_time.axvline(\
		 Ephem.twilight_prev_set+datetime.timedelta(hours=_local_timezone),\
		 color='k', ls='--', lw=2, alpha=0.5, clip_on=True)
		self.thegraph_time.axvline(\
		 Ephem.twilight_next_rise+datetime.timedelta(hours=_local_timezone),\
		 color='k', ls='--', lw=2, alpha=0.5, clip_on=True)

	def make_subplot_sunalt(self,twinplot=0):
		'''
		Make a subplot.
		If twinplot = 0, then this will be the only plot in the figure
		if twinplot = 1, this will be the first subplot
		if twinplot = 2, this will be the second subplot
		'''
		if twinplot == 0:
			self.thegraph_sunalt = self.thefigure.add_subplot()
		else:
			self.thegraph_sunalt = self.thefigure.add_subplot(2,1,twinplot)

		self.thegraph_sunalt.set_title(\
		 'Sky Brightness ('+_device_shorttype+'-'+\
		 _observatory_name+')\n',fontsize='x-large')
		self.thegraph_sunalt.set_xlabel('Solar altitude (deg)',fontsize='large')
		self.thegraph_sunalt.set_ylabel('Sky Brightness (mag/arcsec2)',fontsize='large')

		# format the ticks (frente a alt sol)
		tick_values = range(limits_sunalt[0],limits_sunalt[1]+5,5)
		tick_marks  = np.multiply([deg for deg in tick_values],np.pi/180.0)
		tick_labels = [str(deg) for deg in tick_values]

		self.thegraph_sunalt.set_xticks(tick_marks)
		self.thegraph_sunalt.set_xticklabels(tick_labels)
		self.thegraph_sunalt.yaxis.set_minor_locator(ticker.MultipleLocator(0.5))
		self.thegraph_sunalt.grid(True,which='major')
		self.thegraph_sunalt.grid(True,which='minor')

	def make_subplot_time(self,twinplot=0):
		'''
		Make a subplot.
		If twinplot = 0, then this will be the only plot in the figure
		if twinplot = 1, this will be the first subplot
		if twinplot = 2, this will be the second subplot
		'''
		if twinplot == 0:
			self.thegraph_time = self.thefigure.add_subplot()
		else:
			self.thegraph_time = self.thefigure.add_subplot(2,1,twinplot)

		if _local_timezone<0:
			UTC_offset_label = '-'+str(abs(_local_timezone))
		elif _local_timezone>0:
			UTC_offset_label = '+'+str(abs(_local_timezone))
		else: UTC_offset_label = ''

		#self.thegraph_time.set_title('Sky Brightness (SQM-'+_observatory_name+')',\
		# fontsize='x-large')
		self.thegraph_time.set_xlabel('Time (UTC'+UTC_offset_label+')',fontsize='large')
		self.thegraph_time.set_ylabel('Sky Brightness (mag/arcsec2)',fontsize='large')

		# format the ticks (vs time)
		daylocator	= mdates.HourLocator(byhour=[4,20])
		hourlocator = mdates.HourLocator()
		dayFmt		= mdates.DateFormatter('\n\n%d %b %Y')
		hourFmt	    = mdates.DateFormatter('%H')

		self.thegraph_time.xaxis.set_major_locator(daylocator)
		self.thegraph_time.xaxis.set_major_formatter(dayFmt)
		self.thegraph_time.xaxis.set_minor_locator(hourlocator)
		self.thegraph_time.xaxis.set_minor_formatter(hourFmt)
		self.thegraph_time.yaxis.set_minor_locator(ticker.MultipleLocator(0.5))

		self.thegraph_time.format_xdata = mdates.DateFormatter('%Y-%m-%d_%H:%M:%S')
		self.thegraph_time.grid(True,which='major',ls='')
		self.thegraph_time.grid(True,which='minor')

	def make_figure(self,figsize=(8,8),thegraph_altsun=True,thegraph_time=True):
		# Make the figure and the graph
		self.thefigure = plt.figure(figsize=figsize)
		if thegraph_time==False:
			self.make_subplot_sunalt(twinplot=0)
		elif thegraph_altsun==False:
			self.make_subplot_time(twinplot=0)
		else:
			self.make_subplot_sunalt(twinplot=1)
			self.make_subplot_time(twinplot=2)

		# Adjust the space between plots
		plt.subplots_adjust(hspace=0.25)

	def plot_data(self,Data,Ephem):

		'''
		Warning! Multiple night plot implementation is pending.
		Until the support is implemented, check that no more than 1 night
		is used
		'''

		try:
			assert(np.size(Data.Night)==1)
		except:
			print('Error, more than 1 night in the data file. Check! %d' %np.size(Data.Night))
			raise

		Data.premidnight.filter = np.array(\
		 [Date.date()==Data.Night for Date in Data.premidnight.localdates])
		Data.aftermidnight.filter = np.array(\
		 [(Date-datetime.timedelta(days=1)).date()==Data.Night\
		   for Date in Data.aftermidnight.localdates])

		TheData = Data.premidnight
		if np.size(TheData.filter)>0:
			self.thegraph_sunalt.plot(\
			 np.array(TheData.sun_altitude)[TheData.filter],\
			 np.array(TheData.night_sbs)[TheData.filter],color='g')
			self.thegraph_time.plot(\
			 np.array(TheData.localdates)[TheData.filter],\
			 np.array(TheData.night_sbs)[TheData.filter],color='g')

		TheData = Data.aftermidnight
		if np.size(TheData.filter)>0:
			self.thegraph_sunalt.plot(\
			 np.array(TheData.sun_altitude)[TheData.filter],\
			 np.array(TheData.night_sbs)[TheData.filter],color='b')
			self.thegraph_time.plot(\
			 np.array(TheData.localdates)[TheData.filter],\
			 np.array(TheData.night_sbs)[TheData.filter],color='b')

		# Vertical line to mark 0h
		self.thegraph_time.axvline(\
		 Data.Night+datetime.timedelta(days=1),color='k', alpha=0.5,clip_on=True)

		# Make limits on data range.
		self.thegraph_sunalt.set_xlim([\
		 limits_sunalt[0]*np.pi/180.,\
		 limits_sunalt[1]*np.pi/180.])
		self.thegraph_sunalt.set_ylim(limits_nsb)

		# Set the xlimit for the time plot.

		if np.size(Data.premidnight.filter)>0:
			begin_plot_dt = Data.premidnight.localdates[-1]
			begin_plot_dt = datetime.datetime(\
			 begin_plot_dt.year,\
			 begin_plot_dt.month,\
			 begin_plot_dt.day,\
			 limits_time[0],0,0)
			end_plot_dt = begin_plot_dt+datetime.timedelta(\
			 hours=24+limits_time[1]-limits_time[0])
		elif np.size(Data.aftermidnight.filter)>0:
			end_plot_dt = Data.aftermidnight.localdates[-1]
			end_plot_dt = datetime.datetime(\
			 end_plot_dt.year,\
			 end_plot_dt.month,\
			 end_plot_dt.day,\
			 limits_time[1],0,0)
			begin_plot_dt = end_plot_dt-datetime.timedelta(\
			 hours=24+limits_time[1]-limits_time[0])
		else:
			print('Warning: Cannot calculate plot limits')
			return(None)

		self.thegraph_time.set_xlim(begin_plot_dt,end_plot_dt)

		#self.thegraph_time.set_xlim([limits_time[0]*np.pi/180.,limits_time[1]*np.pi/180.])
		self.thegraph_time.set_ylim(limits_nsb)

		premidnight_label = str(Data.premidnight.label_dates).replace('[','').replace(']','')
		aftermidnight_label = str(Data.aftermidnight.label_dates).replace('[','').replace(']','')

		self.thegraph_time.text(0.00,1.01,\
		 _device_shorttype+'-'+_observatory_name+' '*5+'Serial #'+str(Data.serial_number),\
		 color='0.25',fontsize='small',fontname='monospace',\
		 transform = self.thegraph_time.transAxes)

		self.thegraph_sunalt.text(0.80,0.92,'PM: '+premidnight_label,\
		 color='g',fontsize='small',transform = self.thegraph_sunalt.transAxes)
		self.thegraph_sunalt.text(0.80,0.86,'AM: '+aftermidnight_label,\
		 color='b',fontsize='small',transform = self.thegraph_sunalt.transAxes)
		'''
		self.thegraph_time.text(0.03,0.90,'PM: '+premidnight_label,\
		 color='g',fontsize='small',transform = self.thegraph_time.transAxes)
		self.thegraph_time.text(0.03,0.84,'AM: '+aftermidnight_label,\
		 color='b',fontsize='small',transform = self.thegraph_time.transAxes)
		'''

		if np.size(Data.Night)==1:
			'''
			self.thegraph_time.text(0.03,0.82,'Moon: '+str(int(Ephem.moon_phase))+\
			 '% ('+str(int(Ephem.moon_maxelev*180./np.pi))+'$^\\mathrm{O}$)',\
			 color='r',fontsize='small',transform = self.thegraph_time.transAxes)
			'''
			self.thegraph_sunalt.text(0.797,0.795,'Moon: '+str(int(Ephem.moon_phase))+\
			 '% ('+str(int(Ephem.moon_maxelev*180./np.pi))+'$^\\mathrm{O}$)',\
			 color='r',fontsize='small',transform = self.thegraph_sunalt.transAxes)

	def save_figure(self,output_filename):
		self.thefigure.savefig(output_filename, bbox_inches='tight')

	def show_figure(self):
		plt.show(self.thefigure)

	def close_figure(self):
		plt.close('all')


def save_stats_to_file(Night,NSBData,Ephem):
	'''
	Save statistics to file
	'''

	Stat = NSBData.Statistics

	Header = \
	 '# Summary statistics for '+str(_device_shorttype+'_'+_observatory_name)+'\n'+\
	 '# Description of columns (CSV file):\n'+\
	 '# Col 1: Date\n'+\
	 '# Col 2: Total measures\n'+\
	 '# Col 3: Number of Best NSB measures\n'+\
	 '# Col 4: Median of best N NSBs (mag/arcsec2)\n'+\
	 '# Col 5: Err in the median of best N NSBs (mag/arcsec2)\n'+\
	 '# Col 6: Number of terms of the low-freq fourier model\n'+\
	 '# Col 7: Mean of Abs diff of NSBs data - fourier model (mag/arcsec2)\n'+\
	 '# Col 8: Min Temp (C) between astronomical twilights\n'+\
	 '# Col 9: Max Temp (C) between astronomical twilights\n\n'

	formatted_data = \
		str(Night)+';'+\
		str(Stat.number)+';'+\
		str(Stat.bests_number)+';'+\
		set_decimals(Stat.bests_median,4)+';'+\
		set_decimals(Stat.bests_err,4)+';'+\
		str(Stat.model_nterm)+';'+\
		set_decimals(Stat.data_model_abs_meandiff,3)+';'+\
		set_decimals(Stat.min_temperature,1)+';'+\
		set_decimals(Stat.max_temperature,1)+\
		'\n'

	statistics_filename = \
	 summary_data_directory+'/Statistics_'+\
	 str(_device_shorttype+'_'+_observatory_name)+'.dat'

	print('Writing statistics file')

	def safe_create_file(filename):
		if not os.path.exists(filename):
			open(filename, 'w').close()

	def read_file(filename):
		thefile = open(filename,'r')
		content = thefile.read()
		thefile.close()
		return(content)

	def write_file(filename,content):
		thefile = open(filename,'w')
		thefile.write(content)
		thefile.close()

	def append_file(filename,content):
		thefile = open(filename,'a')
		thefile.write(content)
		thefile.close()

	# Create file if not exists
	safe_create_file(statistics_filename)

	# Read the content
	stat_file_content = read_file(statistics_filename)

	# If the file doesnt have a proper header, add it to the beginning

	def valid_line(line):
		if '#' in line:
			return False
		elif line.replace(' ','')=='':
			return False
		else:
			return True

	if Header not in stat_file_content:
		stat_file_content = [line for line in stat_file_content.split('\n') \
		 if valid_line(line)]
		stat_file_content = '\n'.join(stat_file_content)
		stat_file_content = Header+stat_file_content
		write_file(statistics_filename,stat_file_content)

	# Remove any previous statistic for the given Night in the file
	if str(Night) in stat_file_content:
		stat_file_content = [line for line in stat_file_content.split('\n') \
		 if str(Night) not in line]
		stat_file_content = '\n'.join(stat_file_content)
		write_file(statistics_filename,stat_file_content)

	# Append to the end of the file
	append_file(statistics_filename,formatted_data)


def make_plot(send_emails=False,write_stats=False):
	'''
	Main function (allows to execute the program
	from within python.
	 - Extracts the NSB data from a given data file
	 - Performs statistics
	 - Save statistics to file
	 - Create the plot
	'''

	print('Ploting photometer data ...')

	input_filename  = current_data_directory+\
	 '/'+_device_shorttype+'_'+_observatory_name+'.dat'

	# Define the observatory in ephem
	Ephem = Ephemerids()

	# Get and process the data from input_filename
	NSBData = SQMData(input_filename,Ephem)

	# Moon and twilight ephemerids.
	Ephem.calculate_moon_ephems(thedate=NSBData.Night)
	Ephem.calculate_twilight(thedate=NSBData.Night)

	# Calculate data statistics
	NSBData.data_statistics(Ephem)

	# Write statiscs to file?
	if write_stats==True:
		save_stats_to_file(NSBData.Night,NSBData,Ephem)

	# Plot the data
	NSBPlot = Plot(NSBData,Ephem)

	# Save the plot
	#output_filenames = [\
	#	current_data_directory+'/'+_device_shorttype+'_'+_observatory_name+'.png',\
	#	daily_graph_directory+'/'+_device_shorttype+'_'+_observatory_name+\
	#	 '_'+str(NSBData.Night)+'.png'\
	#	]

	output_filenames = [\
		current_data_directory+'/'+_device_shorttype+'_'+_observatory_name+'.png',\
		daily_graph_directory+'/'+str(NSBData.Night).replace('-','')+'_120000_'+\
		 _device_shorttype+'-'+_observatory_name+'.png'
		]

	for output_filename in output_filenames:
		NSBPlot.save_figure(output_filename)

	# Close figure
	NSBPlot.close_figure()

	if send_emails == True:
		import pysqm_email
		night_label = str(datetime.date.today()-timedelta(days=1))
		pysqm_email.send_emails(night_label=night_label,Stat=NSBData.Statistics)

if __name__ == '__main__':
	# Exec the main program
	make_plot(send_emails=False,write_stats=False)
















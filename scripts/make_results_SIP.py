#!/usr/bin/env python

import os,sys
import siplib
import feedback
import time
import numpy as np
import lofarpipe.support.parset as parset
import get_MOM_data as MOM
import uuid

def input2strlist_nomapfile(invar):
    """ 
    from bin/download_IONEX.py
    give the list of pathes from the list provided as a string
    """
    str_list = None
    if type(invar) is str:
       if invar.startswith('[') and invar.endswith(']'):
          str_list = [f.strip(' \'\"') for f in invar.strip('[]').split(',')]
       else:
          str_list = [invar.strip(' \'\"')]
    elif type(invar) is list:
       str_list = [str(f).strip(' \'\"') for f in invar]
    else:
       raise TypeError('input2strlist: Type '+str(type(invar))+' unknown!')
    return str_list


def input2bool(invar):
    if invar == None:
        return None
    if isinstance(invar, bool):
        return invar
    elif isinstance(invar, str):
        if invar.upper() == 'TRUE' or invar == '1':
            return True
        elif invar.upper() == 'FALSE' or invar == '0':
            return False
        else:
            raise ValueError('input2bool: Cannot convert string "'+invar+'" to boolean!')
    elif isinstance(invar, int) or isinstance(invar, float):
        return bool(invar)
    else:
        raise TypeError('input2bool: Unsupported data type:'+str(type(invar)))

def read_matching_file(matchfile):
    """
    Reads in the match-file generated by sort_times_into_freqGroups.py
    """
    file_matching = {}
    with open(matchfile) as f:
        for line in f:
            parts = line.strip().split()
            file_matching[parts[0]] = parts[1:]
    return file_matching


def get_dataproducts_from_feedback(infile, ID_source):
    """
    Reads in the pseudo feedback file given as input and returns a list of dataproducts.

    Parameters:
    -----------
    infile : str
        path to the feedback file to read in
    ID_source : str
        identifier source for all new identifiers in this pipeline
    """
    dataproducts = []
    with open(infile) as f:
        text = f.readlines()
        FBdata = feedback.Feedback(text)
        prefix = text[0].split('.')[0]
        dataproducts = FBdata.get_dataproducts(prefix=prefix, identifier_source=ID_source)
    return dataproducts

def parset_to_int(parset,key):
    if parset[key].getString().upper() == 'NONE':
        return None
    else:
        return parset[key].getInt()

def parset_to_bool(parset,key):
    if parset[key].getString().upper() == 'NONE':
        return None
    else:
        return parset[key].getBool()


def make_TarPipeline_from_parset(pipeline_name, pipeline_identifier, observation_identifier, ID_source,
                                  starttime, duration,
                                  description_parset, input_dpids):
    """
    Create a calibration pipeline object for the target pipeline

    Parameters:
    -----------
    pipeline_name : str
        Name that identifies this pipeline run.
    pipeline_identifier: siplib.Identifier object
        identifier for this pipeline run 
   observation_identifier: siplib.Identifier object
        identifier for the observation asscociated with this pipeline run 
    ID_source : str
        identifier source for all new identifiers in this pipeline
    starttime : str
        "start"time of this pipeline run in XML format
    duration : str
        "duration" of this pipeline run in XML format
    description_parset : parset object
        parset with additional data fro this pipeline
    input_dpids : list of siplib.Identifier objects
        Identifiers of the input data to this pipeline
    """
    new_pipeline = siplib.CalibrationPipeline(
        siplib.PipelineMap(
            name=pipeline_name,
            version=description_parset['prefactor_version'].getString(),
            sourcedata_identifiers=input_dpids,
            process_map=siplib.ProcessMap(
                strategyname=description_parset['strategyname_target'].getString(),
                strategydescription=description_parset['strategydescription_target'].getString(),
                starttime=starttime,
                duration=duration,
                identifier=pipeline_identifier,
                observation_identifier=observation_identifier,
                relations=[]
                #parset_source=None,
                #parset_id=None
            )
        ),
        skymodeldatabase=description_parset['skymodeldatabase_target'].getString(),
        numberofinstrumentmodels=parset_to_int(description_parset,'numinstrumentmodels'),
        numberofcorrelateddataproducts=parset_to_int(description_parset,'numcorrelateddataproducts'),
        frequencyintegrationstep=parset_to_int(description_parset,'frequencyintegrationstep'),
        timeintegrationstep=parset_to_int(description_parset,'timeintegrationstep'),
        flagautocorrelations=parset_to_bool(description_parset,'flagautocorrelations'),
        demixing=parset_to_bool(description_parset,'demixing')
    )
    return new_pipeline

def get_LTA_frequency_in_Hz(LTAfreq):
    frequency = LTAfreq.value()
    if LTAfreq.units == 'kHz':
        frequency *= 1000.
    elif LTAfreq.units == 'MHz':
        frequency *= 1e6
    return frequency

def get_LTA_Time_in_s(LTAtime):
    timelength = LTAtime.value()
    if LTAtime.units == 'ms':
        timelength /= 1e3
    elif LTAtime.units == 'us':
        timelength /= 1e6
    elif LTAtime.units == 'ns':
        timelength /= 1e9
    return timelength

def time_in_isoformat(timestamp=None):
    import datetime, time
    try:
        return datetime.datetime.utcfromtimestamp(timestamp).isoformat()
    except:
        return datetime.datetime.utcfromtimestamp(time.time()).isoformat()

def main(results_feedback='', input_data_SIP_list=[], instrument_SIP='',
         pipeline_name="", parset_path="",
         verbose = False, fail_on_error = True):
    """
    Generate SIP files for all files mentioned in "results_feedback"
    (Currently results_feedback may only contain one file!)

    results_feedback : str , path
        Path to the feedback file for the pipeline results, generated by the 
        get_metadata recipe.
    input_data_SIP_list : list of str
        list of pathes of xml files that contain the SIPs of the 
        input to the pipeline run
    instrument_SIP : str , path
        Path to the xml file that contains the SIP of the instrument 
        file(s) from the calibrator pipeline
    pipeline_name : str
        Name that identifies this pipeline run
    parset_path : str
        path to the parset with additional information about this version of prefactor
    verbose : bool, (str with bool value)
        Print more output.
    fail_on_error : bool, (str with bool value)
        Stop processing if a recoverable error occurs in one file.
    """
    if not os.path.exists(results_feedback):
        raise ValueError('make_results_SIP: invalid results_feedback')
    input_data_SIP_files = input2strlist_nomapfile(input_data_SIP_list)
    input_data_SIPs = []
    for xmlpath in input_data_SIP_files:
        with open(xmlpath, 'r') as f:
            input_data_SIPs.append(siplib.Sip.from_xml(f.read()))
        f.close()
    if len(input_data_SIPs) <= 0:
        raise ValueError('make_results_SIP: no valid data input SIPs given!')
    with open(instrument_SIP, 'r') as f:
        instrument_SIP = siplib.Sip.from_xml(f.read())
        f.close()
    if len(pipeline_name) <=0:
        raise ValueError('make_results_SIP: invalid pipeline_name')
    if not os.path.exists(parset_path):
        raise ValueError('make_results_SIP: invalid parset_path')
    verbose = input2bool(verbose)
    fail_on_error = input2bool(fail_on_error)
    pipeline_parset = parset.Parset(parset_path)
    identifier_source = pipeline_parset['identifier_source'].getString()

    pipeline_products = get_dataproducts_from_feedback(results_feedback, identifier_source)    
    if len(pipeline_products) > 1:
        raise NotImplementedError('make_results_SIP: Can currently only deal with one dataproduct in the feedback file!')

    created_xml_files = []
    for product in pipeline_products:
        product_identifier = siplib.Identifier(source=identifier_source)
        pipeline_identifier = siplib.Identifier(source=identifier_source)
        # update the dataproduct
        product.set_identifier(product_identifier)
        product.set_process_identifier(pipeline_identifier)
        product.set_subarraypointing_identifier( input_data_SIPs[0].get_dataproduct_subarraypointing_identifier() )
        newsip = siplib.Sip(
            project_code=input_data_SIPs[0].sip.project.projectCode,
            project_primaryinvestigator=input_data_SIPs[0].sip.project.primaryInvestigator,
            project_contactauthor=input_data_SIPs[0].sip.project.contactAuthor,
            project_description=input_data_SIPs[0].sip.project.projectDescription,
            project_coinvestigators=input_data_SIPs[0].sip.project.coInvestigator,
            dataproduct = product
        )
        newsip.add_related_dataproduct_with_history(instrument_SIP)
        input_DPs = [ instrument_SIP.get_dataproduct_identifier() ]
        for inputSIP in input_data_SIPs:
            newsip.add_related_dataproduct_with_history(inputSIP)
            input_DPs.append( inputSIP.get_dataproduct_identifier() )

        # Compute values for the pipeline definition
        input_chan = get_LTA_frequency_in_Hz(input_data_SIPs[0].sip.dataProduct.channelWidth)
        output_chan = get_LTA_frequency_in_Hz(product.get_pyxb_dataproduct().channelWidth)
        freqstep = int(np.round(output_chan/input_chan))
        input_int =  get_LTA_Time_in_s(input_data_SIPs[0].sip.dataProduct.integrationInterval)
        output_int = get_LTA_Time_in_s(product.get_pyxb_dataproduct().integrationInterval)
        timestep = int(np.round(output_int/input_int))
        # update pipeline definition parset
        pipeline_parset.replace('numinstrumentmodels','0')
        pipeline_parset.replace('numcorrelateddataproducts',str(len(pipeline_products)))
        pipeline_parset.replace('frequencyintegrationstep',str(freqstep))
        pipeline_parset.replace('timeintegrationstep',str(timestep))
        # Create the pipeline object for this product
        starttime = time_in_isoformat()
        duration = 'PT1H'
        # for now give the same identifier for the pipeline and the observation
        new_pipeline = make_TarPipeline_from_parset(pipeline_name, pipeline_identifier, pipeline_identifier, 
                                                    identifier_source,
                                                    starttime, duration,
                                                    pipeline_parset, input_DPs)
        newsip.add_pipelinerun(new_pipeline)
        ### save SIP to XML-file
        new_xml_name = product.get_pyxb_dataproduct().fileName.rstrip('/')+".xml"
        newsip.save_to_file(new_xml_name)
        created_xml_files.append(new_xml_name)
        
    return { 'created_xml_files' : created_xml_files }


from flask import render_template, flash, Response
from . import survey_collection
import io
import datetime
import zipfile
import os
from google.cloud import bigquery, bigquery_storage
import pandas as pd
import google.cloud.bigquery.magics

def get_all():
    return survey_collection.get_all()

def get_doc_by_id(id):
    return survey_collection.get_doc_by_id(id)

def get_by_id(id):
    return survey_collection.get_by_id(id)

def delete_by_id(id):
    return survey_collection.delete_by_id(id)

def create(form):
    doc_ref = survey_collection.create(form.data)
    flash(f"{form.surveyName.data} is created as {doc_ref.id}")

def update_by_id(id, form):
    edit_doc = survey_collection.update_by_id(id, form.data)
    flash(f"Survey with ID: {id} is edited")

def set_form_data(form, edit_doc):
    edit_doc_dict = edit_doc.to_dict()
    for key, value in edit_doc_dict.items():
        form[key].data = edit_doc.get(key,)

def zip_file(id):
    # prepare data
    survey_doc = get_doc_by_id(id)
    survey_dict = survey_doc.to_dict()
    current_datetime = datetime.datetime.now().strftime("%Y%m%d")
    surveyName = survey_dict['surveyName'].replace(" ", "-")
    prefix_filename = current_datetime+'_'+surveyName
    seg_types = ['default_control','default_expose']

    # create zip
    write_html_template(id, survey_dict, prefix_filename, seg_types)
    zip_dir(prefix_filename, seg_types)

    # make data response
    filename = prefix_filename +'.zip'
    with open(filename, 'rb') as file:
        file_data = io.BytesIO(file.read())
    delete_tmp_zip_files(prefix_filename, seg_types)
    return filename, file_data

def zip_dir(filename, seg_types):
    zipdir = zipfile.ZipFile(filename+'.zip', 'w', zipfile.ZIP_DEFLATED)
    for seg_type in seg_types:
        zipdir.write(filename+'_'+seg_type+'.zip')

def write_html_template(id, survey_dict, prefix_filename, seg_types):
    
    for seg_type in seg_types:
        dir_name = prefix_filename+'_'+seg_type 
        # write html file
        zip_write_file = zipfile.ZipFile(dir_name+'.zip', 'w', zipfile.ZIP_DEFLATED)
        zip_write_file.writestr('index.html', get_html_template(survey_dict, seg_type))
        

def get_html_template(survey_dict, seg_type):
    return render_template('creative.html',
                            survey=survey_dict,
                            survey_id=id,
                            show_back_button = False,
                            all_question_json=get_question_json(survey_dict),
                            seg=seg_type)

def delete_tmp_zip_files(filename, seg_types):
    for seg_type in seg_types:
        os.remove(filename+'_'+seg_type+'.zip')
    os.remove(filename+'.zip')

def get_question_json(survey):
    all_question_json = []
    for i in range(1, 5):
        question_text = survey.get('question' + str(i), '')
        options = []
        next_question = {}
        question_type = survey.get('question' + str(i) + 'Type')
        if question_text:
            question = {
                'id': i,
                'type': question_type,
                'text': question_text,
                'options': options,
                'next_question': next_question
        }
        for j in ['a', 'b', 'c', 'd']:
            answer_text = survey.get('answer' + str(i) + j, '')
            if answer_text:
                answer_id = j.capitalize()
                options.append({
                    'id': answer_id,
                    'role': 'option',
                    'text': answer_text
                })
            next_question[answer_id] = survey.get('answer' + str(i) + j + 'Next','')
        all_question_json.append(question)
    return all_question_json

def download_results(id):
    google.cloud.bigquery.magics.context.use_bqstorage_api = True
    project_id = os.environ.get("project_id")
    table_id = os.environ.get("table_id")
    client = bigquery.Client(project=project_id)
    bqstorageclient = bigquery_storage.BigQueryReadClient()
    QUERY = f"""
        SELECT *
        FROM `{table_id}`
        LIMIT 1000
    """
    query_job = client.query(QUERY)
    df = (client.query(QUERY)
          .result()
          .to_dataframe(bqstorage_client=bqstorageclient))
    df = df[df['ID']==id]
    output = {'Date':[],'Control/Expose':[],'Dimension 2':[]}
    outputdf = pd.DataFrame(data=output)
    outputdf['Date'] = df['CreatedAt'].values
    responselist = df['Response'].str.split(pat=('|'), expand=True)
    columns = list(responselist)
    for i in columns:
      responselist[i]=responselist[i].str.slice(start=2)
    responselist = responselist.rename(columns={0: 'Response 1', 1: 'Response 2', 2: 'Response 3', 3: 'Response 4'})
    responselist = responselist.reset_index(drop=True)
    outputdf = pd.concat([outputdf, responselist], axis=1)
    print (outputdf)
    csv = outputdf.to_csv()
    return csv
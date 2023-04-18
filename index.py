import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import matplotlib.pyplot as plt
import pandas as pd
import requests
import seaborn as sns
from census import Census
from us import states
from census import CensusException

# configure logging
logger = logging.getLogger(__name__)
stream_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(stream_handler)
logger.setLevel(logging.INFO)

try:
    # Insert your API token key as first argument. The 5 year census data pulls up to 2021.
    logger.info('Authenticating API Token Key....')
    c = Census("INSERT API KEY HERE", year=2021)
except CensusException:
    logger.error('Please provide a valid API Token Key!')
    sys.exit(1)

try:
    # Specify the state
    state_abbreviation = sys.argv[1].upper()
    state = getattr(states, state_abbreviation).fips
except AttributeError:
    logger.error('Please provide a valid US state abbreviation!')
    logger.error('Stopping the script....')
    sys.exit(1)

"""A variable is each unit of data you are searching for in a dataset.  Each variable that you can 
search for in a dataset has a name"""

males_age = ['B01001_003E', 'B01001_004E', 'B01001_005E', 'B01001_006E', 'B01001_007E', 'B01001_008E', 'B01001_009E', 'B01001_010E', 'B01001_011E', 'B01001_012E', 'B01001_013E',
             'B01001_014E', 'B01001_015E', 'B01001_016E', 'B01001_017E', 'B01001_018E', 'B01001_019E', 'B01001_020E', 'B01001_021E', 'B01001_022E', 'B01001_023E', 'B01001_024E', 'B01001_025E']

females_age = ['B01001_027E', 'B01001_028E', 'B01001_029E', 'B01001_030E', 'B01001_031E', 'B01001_032E', 'B01001_033E', 'B01001_034E', 'B01001_035E', 'B01001_036E', 'B01001_037E',
               'B01001_038E', 'B01001_039E', 'B01001_040E', 'B01001_041E', 'B01001_042E', 'B01001_043E', 'B01001_044E', 'B01001_045E', 'B01001_046E', 'B01001_047E', 'B01001_048E', 'B01001_049E']


def getData(dataset_var, gender, state):

    logger.info(f'Fetching {gender} dataset variable lables to populate the graph!')
    url = 'https://api.census.gov/data/2019/acs/acs5/variables.json'
    response = requests.get(url)
    data = json.loads(response.text)
    variables = data['variables']

    var_lst = []
    data_dict = {}
    result_dict = {}

    # clean up labels extracted from census webpage for dataset variables
    logger.info(f'Cleaning up the {gender} label to pretty print..')
    for item in dataset_var:
        label = variables[item]['label']
        new_label = re.search(r'\d.*(?=\syears)', label).group()
        if 'and over' in new_label:
            new_label = new_label.replace('and over', '+')
        elif 'to' in new_label:
            new_label = new_label.replace('to', '-')
        elif 'and' in new_label:
            new_label = new_label.replace('and', '-')
        elif re.search(r'^\d$', new_label):
            new_label = f'0 - {new_label}'
        labels = {item: new_label}
        var_lst.append(labels)

    # get data from 5 year census based on variables
    logger.info(f'Calling API to fetch {gender} data from US Census..')
    for variables in var_lst:
        for k, v in variables.items():
            m_data = c.acs5.get(('NAME', k), {'for': f'state:{state}'})
            result = m_data[0][k]
            # graph data to represent males on the left side
            if gender == 'Males':
                result = int(result) * -1
            else:
                result = int(result)
            # group ages by decades
            age_range = v.split(' - ')
            if len(age_range) == 2:
                start_age = int(age_range[0])
                end_age = int(age_range[1])
            else:
                start_age = end_age = int(age_range[0])
            decade = f"{start_age // 10 * 10} - {end_age // 10 * 10 + 9}"

            result_dict[decade] = result_dict.get(decade, 0) + result

    data_lst = [result_dict]

    # data frame pre-cleaning to keep the values in one column
    for d in data_lst:
        for key, value in d.items():
            data_dict.setdefault(key, []).append(value)

    nes_dict = {
        gender: data_dict.values(),
        'Age Group': data_dict.keys()}

    logger.info(f'Creating {gender} dataframe...')
    df = pd.DataFrame(nes_dict)
    df = df.sort_index(ascending=False)

    return df


def consolidateDF(df, df2):

    df = df.explode('Males')
    df2 = df2.explode('Females')

    result = pd.merge(df, df2, on='Age Group')
    result = result.reindex(columns=['Age Group', 'Males', 'Females'])
    logger.info('Consolidation of male and female data complete!')

    return result


def createGraph(data, state):

    logger.info(f'Creating {state} pyramid bar graph...')
    filename = f'population_pyramid_{state_abbreviation}.pdf'
    AgeClass = data['Age Group']

    # Melt the data to long format
    data_melted = data.melt(id_vars='Age Group', value_vars=[
                            'Males', 'Females'], var_name='Gender', value_name='Population')

    # Create a bar plot with hue set to 'Gender' and dodge set to False
    bar_plot = sns.barplot(x='Population', y='Age Group', hue='Gender',
                           dodge=False, data=data_melted, order=AgeClass, lw=0)

    # Set the x-axis label based on whether any value in the Females column is greater than one million
    if (data['Females'] > 1000000).any():
        bar_plot.set(xlabel=f"Population in millions",
                     ylabel="Age Group", title=f"Population of {state} 2021")
    else:
        bar_plot.set(xlabel="Population in thousands",
                     ylabel="Age Group", title=f"Population of {state} 2021")

    # Save the graph to a file
    logger.info(f'Saving the graph to a file called {filename}')
    plt.savefig(filename)


def main():

    # Define the arguments for each call to getData
    getData_args = [
        (males_age, 'Males', state),
        (females_age, 'Females', state)]

    # Use a ThreadPoolExecutor to call getData with different arguments in parallel
    with ThreadPoolExecutor() as executor:
        results = executor.map(lambda args: getData(*args), getData_args)

    # Unpack the results
    df, df2 = results

    data = consolidateDF(df, df2)
    createGraph(data, state_abbreviation)

if __name__ == "__main__":
    main()

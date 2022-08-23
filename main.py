import yaml
import logging

from connector import github

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    OLD_ORG = "<>"
    NEW_ORG = "<>"
    PAT = "<>"
    with open("conf/secret_database.yaml") as f:
        secret_database = yaml.load(f, Loader=yaml.FullLoader)

    gh = github.Github(OLD_ORG, NEW_ORG, PAT)

    # #######################################
    # list all repositories
    # return ['a','b','c']
    logging.info('get all repositories from new organization')
    res = gh.list_repositories(org_from='new')
    repositories = []
    for repository in res:
        repositories.append(repository['full_name'].split('/')[1])
    logging.info(repositories)
    # #######################################

    # ########################################
    # list organization secrets
    # return ['name','name']
    logging.info('get organization secrets from old organization')
    list_org_secret = gh.list_org_secrets()
    logging.info(list_org_secret)
    # ########################################

    # ########################################
    # list secret by repo
    # return {'name':['a','b']}
    logging.info('get secrets by repository from old organization')
    list_secret_by_repo = gh.list_repo_secret(repositories)
    logging.info(list_secret_by_repo)
    # ########################################

    # ########################################
    # # create organization secret

    # from list org secrets
    logging.info('Create organization secrets into new organization')
    for secret_name in list_org_secret:
        secret_value = secret_database.get(secret_name, None)
        if not secret_value:
            continue

        gh.create_organization_secret(secret_name, secret_value)
    # ########################################

    # ########################################
    # # create repository secret
    logging.info('Create secret by repository into new organization')
    gh.create_repo_secret(list_secret_by_repo, secret_database)
    # ########################################




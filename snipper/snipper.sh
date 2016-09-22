#!/bin/bash


USERNAME=$BITBUCKET_USER
PASSWORD=$BITBUCKET_PASSWORD

# Bitbucket offer only http basic authentication(user/password) method.
# Not offering token authentication for now.
# You can create a app password on
# Bitbucket > Settings > App passwords
# permitted for only snippets.
# Use the password for using Bitbucket API.

SNIPPET_DIR="$HOME/.snippets"

BASE_API_URI='https://api.bitbucket.org/2.0'

# Set 0 for https
CLONE_REPO_WITH_SSH=1


function help {
cat << EOF
Usage of $0:
    ls
        List all snippets
    find
        Search text in local snippets
    sync
        Sync local snippet repos from bitbucket.org
EOF
}

function createTempFile {
    echo $(mktemp)
}

function slugify {
    echo "$@" | iconv -t ascii//TRANSLIT | sed -r 's/[^a-zA-Z0-9]+/-/g' | sed -r 's/^-+\|-+$//g' | tr A-Z a-z
}

function downloadResource {
    tmpFile=$(createTempFile)
    curl --silent -o $tmpFile -u $USERNAME:$PASSWORD $1
    echo $tmpFile
}

function cloneGitSnippet {
    git clone $1 $2 > /dev/null 2>&1
}

function updateGitSnippets {
    # Pull new changes from remote.
    for dir in $SNIPPET_DIR/*/*/ ; do
        echo "Updating: $dir"
        git --git-dir=$dir/.git pull > /dev/null 2>&1
    done
}

function syncSnippets {
    # Sync remote with local
    # clone new snippets and update existing snippets

    tmpFile=$(downloadResource "$BASE_API_URI/snippets/$USERNAME")
    fileContent=$(cat $tmpFile)

    updateGitSnippets

    i=0
    echo $fileContent | jq -r ".values[].links.clone[$CLONE_REPO_WITH_SSH].href" | \
    while read cloneUri
     do
        snippetId=$(echo $fileContent | jq -r ".values[$i].id")
        snippetOwner=$(echo $fileContent | jq -r ".values[$i].owner.username")

        # Dont use title for directory naming
        # because title changable from web
        cloneTo="$SNIPPET_DIR/$snippetOwner/$snippetId"

        if [ ! -d $cloneTo ]; then
            title=$(echo $fileContent | jq -r --arg i "$i" ".values[$i].title")
            echo "[Downloading Snippet]: $title"
            cloneGitSnippet $cloneUri $cloneTo
        fi

        i=${i+1}
    done

}

function listRemoteSnippets {
    tmpFile=$(downloadResource "$BASE_API_URI/snippets/$USERNAME")
    fileContent=$(cat $tmpFile)
    i=0
    echo $fileContent | jq -r '.values[] | "[" + .id + "] " + .title' | \
    while read item
    do
        echo "$item"
        i=${i+1}
    done
}


while [[ $# -gt 0 ]]; do

case $1 in
    help|--help|-h)
    help
    shift # past argument
    ;;
    ls)
    listRemoteSnippets
    shift # past argument
    ;;
    sync)
    syncSnippets
    shift # past argument
    ;;
    *)
    # unknown option
    ;;
esac
shift # past argument or value
done

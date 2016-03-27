for bisec in "B1" "B6" "B12"
do
    for topo in "jellyfish" "egft"
    do
        ./tree_fail_parse.py --results fail $bisec/*.$topo.*
        ./tree_fail_parse.py --results tput $bisec/*.$topo.*
    done
done

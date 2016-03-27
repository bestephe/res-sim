for bisec in "B1" "B6"
do
    for topo in "jellyfish" "egft"
    do
        for model in line2 T alayer mlayer rand maxdag
        do
            echo Gathering $bisec $topo $model
            ./tree_fail_parse.py --prefix $model --results fail $bisec/*.$topo.*$model* $bisec/*.$topo.*no*-t.*
            ./tree_fail_parse.py --prefix $model --results tput $bisec/*.$topo.*$model* $bisec/*.$topo.*no*-t.*
        done
    done
done

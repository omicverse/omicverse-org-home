args <- commandArgs(trailingOnly=TRUE)
if (length(args) < 1) stop('Supply the workspace root as the first argument')
workspace <- normalizePath(args[[1]], winslash='/')
root <- workspace
.libPaths(c(file.path(root,'outputs/rewrite-validation/R-library'),.libPaths()))
source(file.path(root,'repos/reference-cytotrace/R/CytoTRACE.R'))
out <- file.path(root,'outputs/rewrite-validation/report-v2/cyto')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
timings <- list()
for (dataset in c('marrow_10x','marrow_plate')) {
  load(file.path(root,'repos/reference-cytotrace/data',paste0(dataset,'_expr.rda')))
  mat <- get(paste0(dataset,'_expr'))
  for (n in c(100,200,400)) {
    set.seed(17); idx <- sort(sample(seq_len(ncol(mat)), min(n,ncol(mat))))
    x <- as.matrix(mat[,idx]); tag <- paste0(dataset,'_',n)
    write.csv(x,file.path(out,paste0(tag,'_input.csv')))
    start <- proc.time()[['elapsed']]
    result <- CytoTRACE(x,enableFast=FALSE,ncores=1)
    elapsed <- proc.time()[['elapsed']]-start
    write.csv(data.frame(cell=colnames(x),score=result$CytoTRACE,rank=result$CytoTRACErank,
                        counts=result$Counts,gcs=result$GCS),file.path(out,paste0(tag,'_r.csv')),row.names=FALSE)
    write.csv(data.frame(gene=names(result$cytoGenes),r=result$cytoGenes),file.path(out,paste0(tag,'_r_genes.csv')),row.names=FALSE)
    timings[[tag]] <- data.frame(dataset=dataset,n=n,genes=nrow(x),seconds=elapsed,max_input=max(x))
    print(timings[[tag]])
  }
}
write.csv(do.call(rbind,timings),file.path(out,'r_timings.csv'),row.names=FALSE)
writeLines(capture.output(sessionInfo()),file.path(out,'sessionInfo.txt'))

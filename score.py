class result:
	def __init__(self, id, tx, ty, rmse, num, len, score ):
		self.id 	= id
		self.tx		= tx
		self.ty		= ty
		self.rmse	= rmse
		self.num	= num
		self.len	= len
		self.score	= score
	
	def __repr__(self):
		return repr((self.id, self.tx, self.ty, self.rmse, self.num, self.len, self.score))
		

def best(results):
	best = sorted( results, key=lambda result: result.num, reverse=True )
	return best[0]
	
#
# Testing
#
if __name__ == "__main__":	
	data = [
		result(1, 97, -356, 368.305580, 98, 128, 0),
		result(2, 97, -356, 368.328658, 123, 131, 0),
		result(3, 97, -355, 367.929341, 15, 17, 0)
	]
	
	best = best(data)
	print best.tx, best.ty
